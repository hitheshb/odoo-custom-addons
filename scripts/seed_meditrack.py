"""Seed the meditrack module with doctors, patients and appointments over RPC.

Uses Odoo's JSON-2 API (POST /json/2/<model>/<method>), the replacement for
the XML-RPC / JSON-RPC endpoints that were deprecated in Odoo 19.

Usage:
    export ODOO_API_KEY=...   # Preferences -> Account Security -> New API Key
    python3 scripts/seed_meditrack.py
"""
import os
from datetime import datetime, timedelta, timezone

import requests

URL = os.environ.get('ODOO_URL', 'http://localhost:8070')
DB = os.environ.get('ODOO_DB', 'odoo20')
API_KEY = os.environ['ODOO_API_KEY']

session = requests.Session()
session.headers.update({
    'Authorization': f'bearer {API_KEY}',
    'X-Odoo-Database': DB,
})


def call(model, method, ids=(), **kwargs):
    """Call ``model.method(**kwargs)`` on the server and return the JSON result."""
    payload = dict(kwargs)
    if ids:
        payload['ids'] = list(ids)
    response = session.post(f'{URL}/json/2/{model}/{method}', json=payload)
    if not response.ok:
        raise RuntimeError(f'{model}.{method} failed ({response.status_code}): {response.text}')
    return response.json()


def get_or_create_partner(vals):
    """Return the id of the partner named ``vals['name']``, creating it if missing."""
    existing = call('res.partner', 'search', domain=[('name', '=', vals['name'])], limit=1)
    if existing:
        return existing[0]
    return call('res.partner', 'create', vals_list=[vals])[0]


def utc(local_dt, tz_offset=timedelta(hours=5, minutes=30)):
    """Convert a naive Asia/Calcutta datetime to the UTC string Odoo stores."""
    return (local_dt - tz_offset).strftime('%Y-%m-%d %H:%M:%S')


DOCTORS = [
    {'name': 'Dr. Anita Rao', 'is_doctor': True, 'specialization': 'cardiology',
     'license_number': 'KMC-10231', 'years_of_experience': 14},
    {'name': 'Dr. Suresh Menon', 'is_doctor': True, 'specialization': 'general',
     'license_number': 'KMC-20877', 'years_of_experience': 8},
    {'name': 'Dr. Kavya Iyer', 'is_doctor': True, 'specialization': 'pediatrics',
     'license_number': 'KMC-31540', 'years_of_experience': 5},
]

PATIENTS = [
    {'name': 'Ravi Kumar', 'is_patient': True, 'date_of_birth': '1988-03-14', 'blood_group': 'b+'},
    {'name': 'Meera Nair', 'is_patient': True, 'date_of_birth': '1995-11-02', 'blood_group': 'o+'},
    {'name': 'Arjun Shetty', 'is_patient': True, 'date_of_birth': '2018-07-21', 'blood_group': 'a-'},
    {'name': 'Lakshmi Devi', 'is_patient': True, 'date_of_birth': '1956-01-30', 'blood_group': 'ab+'},
]


def main():
    doctors = {vals['name']: get_or_create_partner(vals) for vals in DOCTORS}
    patients = {vals['name']: get_or_create_partner(vals) for vals in PATIENTS}

    tomorrow = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30, days=1)
    tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    appointments = [
        ('Ravi Kumar', 'Dr. Anita Rao', tomorrow.replace(hour=10), 'Chest pain follow-up', 'confirmed'),
        ('Meera Nair', 'Dr. Suresh Menon', tomorrow.replace(hour=11, minute=30), 'Fever and cold', 'draft'),
        ('Arjun Shetty', 'Dr. Kavya Iyer', tomorrow.replace(hour=15), 'Vaccination', 'confirmed'),
        ('Lakshmi Devi', 'Dr. Anita Rao', (tomorrow - timedelta(days=3)).replace(hour=9), 'BP check', 'done'),
    ]
    appointment_ids = call('hospital.appointment', 'create', vals_list=[
        {
            'patient_id': patients[patient],
            'doctor_id': doctors[doctor],
            'appointment_date': utc(when),
            'reason': reason,
            'status': status,
        }
        for patient, doctor, when, reason, status in appointments
    ])

    for record in call('res.partner', 'read', ids=list(doctors.values()) + list(patients.values()),
                       fields=['name', 'doctor_ref', 'patient_ref', 'age']):
        print(record)
    for record in call('hospital.appointment', 'read', ids=appointment_ids,
                       fields=['name', 'patient_id', 'doctor_id', 'appointment_date', 'status']):
        print(record)


if __name__ == '__main__':
    main()
