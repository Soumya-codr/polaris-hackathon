"""Local relevance demo. Not the scored benchmark.

Usage: python demo_queries.py
"""
import time

from search import Catalog


QUERIES = [
    {'query': 'black dress under INR 2000', 'limit': 5},
    {'query': 'Black jeans and white T-shirts under INR 2000 each',
     'filters': {'audience': 'Ladieswear', 'max_price': 2000}, 'limit': 8},
    {'query': 'A dress for dinner under INR 2000 with a matching bag under INR 1000',
     'include_recommendations': True, 'limit': 5},
    {'query': 'something comfortable for a lazy Sunday', 'limit': 6},
    {'query': 'blak lether jaket for men', 'limit': 5},
    {'query': 'spaceship engine', 'limit': 5},
    {'query': 'navy chinos for the office', 'limit': 5},
    {'query': 'red dress or blue skirt', 'limit': 6},
]


def brief(catalog, product_id):
    product = catalog.products[catalog.id_index[product_id]]
    rating = product['rating']['average']
    rating_text = 'unrated' if rating is None else f'{rating:.1f}'
    return (f"{product['id']}  {product['product_type'][:22]:<22} {product['color'][:16]:<16} "
            f"{product['audience'][:18]:<18} INR {product['price']['amount']:<5} {rating_text:<6} {product['name']}")


def main():
    started = time.perf_counter()
    catalog = Catalog.load('data/products.json')
    print(f'loaded {catalog.n} products in {time.perf_counter() - started:.2f}s')
    assert catalog.n == 105126
    for arguments in QUERIES:
        cold = None
        for attempt in range(2):
            t0 = time.perf_counter()
            result = catalog.search(dict(arguments))
            elapsed = (time.perf_counter() - t0) * 1000
            if attempt == 0:
                cold = elapsed
        print(f"\n== {arguments['query']}  cold {cold:.1f} ms, repeat {elapsed:.1f} ms ==")
        if not result['results']:
            print('  (no results)')
        for item in result['results']:
            print(' ', brief(catalog, item['id']))
        for item in result['recommendations']:
            print('  +', brief(catalog, item['id']))
            print('   ', item['reason'], 'for', item['for_product_id'])
    repeats = []
    for _ in range(30):
        t0 = time.perf_counter()
        page = catalog.search({'filters': {'color': 'Black', 'max_price': 2000},
                               'sort_by': 'price', 'sort_order': 'asc', 'limit': 10})
        repeats.append((time.perf_counter() - t0) * 1000)
    repeats.sort()
    print(f"\nempty-query price sort p50 {repeats[len(repeats)//2]:.2f} ms  p95 {repeats[int(len(repeats)*0.95)-1]:.2f} ms")
    assert page['results'], page
    prices = [catalog.products[catalog.id_index[item['id']]]['price']['amount'] for item in page['results']]
    assert prices == sorted(prices), prices
    assert catalog.search({'query': 'spaceship engine'}) == {'results': [], 'recommendations': []}
    first = catalog.search({'query': 'cotton', 'limit': 10})
    second = catalog.search({'query': 'cotton', 'limit': 10})
    assert first == second
    print('checks passed')


if __name__ == '__main__':
    main()
