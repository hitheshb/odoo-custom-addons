"""Seed grocery_management with 50 test records per model, over the JSON-2 RPC API.

grocery.sale.line has no standalone create path in the UI (it's a One2many
on grocery.sale), so its 50 records are created by spreading them across the
50 grocery.sale records via line_ids commands - the same way a real sale form
would create them.

Usage:
    export ODOO_API_KEY=...   # RPC-scope key, see scripts/seed_meditrack.py
    python3 scripts/seed_grocery.py
"""
import os
import random
from datetime import datetime, timedelta

import requests

URL = os.environ.get('ODOO_URL', 'http://localhost:8070')
DB = os.environ.get('ODOO_DB', 'odoo20')
API_KEY = os.environ['ODOO_API_KEY']

session = requests.Session()
session.headers.update({
    'Authorization': f'bearer {API_KEY}',
    'X-Odoo-Database': DB,
})

random.seed(42)  # reproducible test data


def call(model, method, ids=(), **kwargs):
    payload = dict(kwargs)
    if ids:
        payload['ids'] = list(ids)
    response = session.post(f'{URL}/json/2/{model}/{method}', json=payload)
    if not response.ok:
        raise RuntimeError(f'{model}.{method} failed ({response.status_code}): {response.text}')
    return response.json()


BRANDS = ['Nestle', 'Amul', 'ITC', 'Tata', 'Britannia', 'Parle', 'Dabur', 'Local Farm']
CATEGORIES = ['Dairy', 'Snacks', 'Beverages', 'Produce', 'Bakery', 'Grains', 'Spices', 'Frozen']
PRODUCT_WORDS = ['Milk', 'Bread', 'Rice', 'Sugar', 'Salt', 'Oil', 'Tea', 'Coffee', 'Biscuits',
                  'Juice', 'Paneer', 'Butter', 'Curd', 'Wheat Flour', 'Chips', 'Noodles',
                  'Cereal', 'Honey', 'Jam', 'Sauce', 'Pickle', 'Ghee', 'Yogurt', 'Cheese', 'Eggs']


def seed_products(n=50):
    """Create n grocery.product records. Returns: list[int] of their ids."""
    today = datetime.now().date()
    vals_list = []
    for i in range(n):
        word = PRODUCT_WORDS[i % len(PRODUCT_WORDS)]
        cost = round(random.uniform(10, 300), 2)
        vals_list.append({
            'name': f'{word} {i + 1}',
            'brand': random.choice(BRANDS),
            'category': random.choice(CATEGORIES),
            'cost_price': cost,
            'selling_price': round(cost * random.uniform(1.15, 1.6), 2),
            # spread quantities around the default low-stock threshold so
            # is_low_stock ends up True for some and False for others
            'quantity': random.choice([0, 2, 4, 5, 8, 15, 30, 60, 100]),
            'quality': random.choice(['0', '1', '2', '3', '4', '5']),
            'expiry_date': (today + timedelta(days=random.randint(-10, 180))).isoformat(),
        })
    return call('grocery.product', 'create', vals_list=vals_list)


FIRST_NAMES = ['Ravi', 'Priya', 'Arjun', 'Sneha', 'Vikram', 'Anjali', 'Karthik', 'Divya',
               'Manoj', 'Pooja', 'Suresh', 'Kavya', 'Rahul', 'Neha', 'Arun', 'Meera',
               'Sanjay', 'Lakshmi', 'Deepak', 'Swathi']
LAST_NAMES = ['Kumar', 'Sharma', 'Iyer', 'Nair', 'Reddy', 'Rao', 'Menon', 'Gupta', 'Shetty', 'Pillai']


def seed_customers(n=50):
    """Create n grocery.customer records. Returns: list[int] of their ids."""
    vals_list = []
    seen = set()
    for i in range(n):
        while True:
            name = f'{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}'
            if name not in seen:
                seen.add(name)
                break
        vals_list.append({
            'name': name,
            'phone': f'9{random.randint(100000000, 999999999)}',
            'email': f'{name.lower().replace(" ", ".")}{i}@example.com',
            'address': f'{random.randint(1, 999)} MG Road, Bengaluru',
        })
    return call('grocery.customer', 'create', vals_list=vals_list)


def seed_sales_and_lines(customer_ids, product_ids, n_sales=50, n_lines=50):
    """Create n_sales grocery.sale records carrying n_lines grocery.sale.line
    records total between them (each sale gets >=1 line).

    grocery.sale.create() deducts stock for every line on a sale created as
    'approved', and checks availability summed across the WHOLE create()
    batch (see GrocerySale._deduct_stock_for_approval). So approved lines
    here only draw from products.quantity > 0, and running demand per
    product is tracked so the batch total never exceeds what's on hand.
    draft lines are unconstrained, since draft never deducts stock.

    Returns: (list[int] sale ids, int total line count created)
    """
    stock = call('grocery.product', 'read', ids=product_ids, fields=['quantity'])
    remaining = {rec['id']: rec['quantity'] for rec in stock if rec['quantity'] > 0}
    in_stock_ids = list(remaining)

    today = datetime.now()
    # distribute n_lines across n_sales, each sale gets at least 1 line
    lines_per_sale = [1] * n_sales
    for _ in range(n_lines - n_sales):
        lines_per_sale[random.randrange(n_sales)] += 1

    vals_list = []
    for i in range(n_sales):
        state = random.choice(['draft', 'draft', 'approved'])  # more draft than approved
        line_commands = []
        for _ in range(lines_per_sale[i]):
            if state == 'approved' and in_stock_ids:
                product_id = random.choice(in_stock_ids)
                qty = min(random.randint(1, 10), remaining[product_id])
                remaining[product_id] -= qty
                if remaining[product_id] <= 0:
                    in_stock_ids.remove(product_id)
            elif state == 'approved':
                # every in-stock product already spoken for this batch - fall back to draft
                state = 'draft'
                product_id = random.choice(product_ids)
                qty = random.randint(1, 10)
            else:
                product_id = random.choice(product_ids)
                qty = random.randint(1, 10)
            line_commands.append((0, 0, {
                'product_id': product_id,
                'quantity': qty,
                'price': round(random.uniform(10, 350), 2),
            }))
        vals_list.append({
            'customer_id': random.choice(customer_ids),
            'sale_date': (today - timedelta(days=random.randint(0, 60),
                                              hours=random.randint(0, 23))).strftime('%Y-%m-%d %H:%M:%S'),
            'state': state,
            'line_ids': line_commands,
        })
    sale_ids = call('grocery.sale', 'create', vals_list=vals_list)
    return sale_ids, sum(lines_per_sale)


def main():
    # resumable: if a previous run already created the 50 products/customers
    # (this run's create() calls are atomic - a raised error rolls the whole
    # batch back), reuse them instead of creating a second set of 50.
    existing_products = call('grocery.product', 'search', domain=[], limit=100)
    if len(existing_products) >= 50:
        product_ids = existing_products[:50]
        print(f'reusing {len(product_ids)} existing grocery.product records')
    else:
        product_ids = seed_products(50)
        print(f'created {len(product_ids)} grocery.product records')

    existing_customers = call('grocery.customer', 'search', domain=[], limit=100)
    if len(existing_customers) >= 50:
        customer_ids = existing_customers[:50]
        print(f'reusing {len(customer_ids)} existing grocery.customer records')
    else:
        customer_ids = seed_customers(50)
        print(f'created {len(customer_ids)} grocery.customer records')

    sale_ids, line_count = seed_sales_and_lines(customer_ids, product_ids, n_sales=50, n_lines=50)
    print(f'created {len(sale_ids)} grocery.sale records carrying {line_count} grocery.sale.line records')

    # quick sanity read-back
    sample = call('grocery.sale', 'read', ids=sale_ids[:3],
                   fields=['name', 'customer_id', 'state', 'amount_total', 'line_ids'])
    for rec in sample:
        print(rec)


if __name__ == '__main__':
    main()
