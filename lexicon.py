"""Query understanding for the frozen fashion catalog.

Phrase tables are grounded in catalog values. They do not invent products.
"""
import re
from dataclasses import dataclass

STOP = frozenset({
    'a', 'an', 'the', 'and', 'or', 'for', 'to', 'of', 'in', 'on', 'at', 'by', 'with',
    'from', 'into', 'onto', 'this', 'that', 'these', 'those', 'it', 'its', 'my', 'me',
    'i', 'im', 'you', 'your', 'we', 'our', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'am', 'want', 'wants', 'looking', 'look', 'show', 'find', 'please',
    'need', 'needs', 'get', 'some', 'something', 'anything', 'everything', 'just',
    'really', 'very', 'also', 'too', 'can', 'could', 'would', 'should', 'wear',
    'wearing', 'outfit', 'outfits', 'clothes', 'clothing', 'item', 'items', 'product',
    'products', 'pair', 'pairs', 'matching', 'match', 'complement', 'complementary',
    'under', 'below', 'over', 'above', 'between', 'than', 'less', 'more', 'upto',
    'up', 'each', 'inr', 'rs', 'rupee', 'rupees', 'price', 'priced', 'budget', 'only',
    'about', 'around', 'approx', 'both', 'all', 'any', 'few', 'one', 'two', 'style',
    'styled', 'looks', 'like', 'suitable', 'perfect', 'great', 'good', 'nice', 'buy',
    'shopping', 'shop', 'search', 'thanks', 'thank', 'color', 'colour', 'colored',
    'coloured', 'size', 'sizes', 'sized', 'which', 'what', 'when', 'where', 'who',
    'how', 'do', 'does', 'did', 'have', 'has', 'had', 'but', 'so', 'if', 'then',
    'not', 'no', 'yes', 'ok', 'okay', 'please', 'kind', 'sort', 'type', 'types',
    'made', 'using', 'use', 'featuring', 'feature', 'features', 'day', 'days',
    'night', 'today', 'tomorrow', 'someone', 'someone', 'idea', 'ideas', 'option',
    'options', 'recommend', 'suggest', 'suggestion', 'complete', 'look',
})

ADJECTIVES = frozenset({
    'comfortable', 'comfy', 'beautiful', 'pretty', 'cute', 'stylish', 'elegant',
    'chic', 'trendy', 'soft', 'warm', 'cool', 'lovely', 'gorgeous', 'casual',
    'cozy', 'fancy', 'simple', 'basic', 'modern', 'classic', 'unique', 'awesome',
    'amazing', 'nice', 'great', 'lightweight', 'breathable', 'stretchy', 'fitted',
    'loose', 'oversized', 'slim', 'relaxed', 'smart', 'sharp', 'classy', 'sexy',
    'modest', 'vibrant', 'bold', 'subtle', 'plain', 'fancy', 'premium', 'luxury',
    'luxurious', 'cheap', 'affordable', 'budget', 'inexpensive', 'expensive',
    'best', 'toprated', 'quality', 'rated', 'rating', 'popular', 'favourite',
    'favorite', 'beautiful', 'gorgeous', 'elegant',
})

OOD = frozenset({
    'spaceship', 'spacecraft', 'rocket', 'engine', 'laptop', 'computer', 'iphone',
    'android', 'textbook', 'calculus', 'bitcoin', 'crypto', 'cryptocurrency',
    'fridge', 'refrigerator', 'pizza', 'burger', 'quantum', 'molecule', 'nasa',
    'airplane', 'aircraft', 'submarine', 'minecraft', 'playstation', 'xbox',
    'homework', 'equation', 'mortgage', 'vaccine', 'antivirus', 'carburetor',
    'toyota', 'honda', 'bmw', 'mercedes', 'tesla', 'iphone', 'ipad', 'galaxy',
    'python', 'javascript', 'kubernetes', 'docker', 'database', 'sql', 'nft',
    'forex', 'stock', 'stocks', 'weapon', 'rifle', 'ammo', 'pistol', 'gun',
    'car', 'truck', 'suv', 'motorcycle', 'bicycle', 'laptop', 'printer',
    'refrigerator', 'microwave', 'toaster', 'blender',
})

# Base color word -> exact catalog color values (casefold).
COLOR_GROUPS = {
    'black': ('black',),
    'white': ('white', 'off white'),
    'off white': ('off white',),
    'offwhite': ('off white',),
    'cream': ('off white', 'beige', 'light beige'),
    'ivory': ('off white', 'beige'),
    'navy': ('dark blue',),
    'gray': ('grey', 'dark grey', 'light grey'),
    'grey': ('grey', 'dark grey', 'light grey'),
    'charcoal': ('dark grey',),
    'khaki': ('greenish khaki',),
    'beige': ('beige', 'light beige', 'dark beige', 'greyish beige'),
    'tan': ('beige', 'yellowish brown', 'light beige'),
    'brown': ('yellowish brown',),
    'pink': ('pink', 'light pink', 'dark pink', 'other pink'),
    'red': ('red', 'dark red', 'light red', 'other red'),
    'blue': ('blue', 'dark blue', 'light blue', 'other blue'),
    'green': ('green', 'dark green', 'light green', 'other green', 'greenish khaki'),
    'yellow': ('yellow', 'light yellow', 'dark yellow', 'other yellow', 'yellowish brown'),
    'orange': ('orange', 'light orange', 'dark orange', 'other orange'),
    'purple': ('purple', 'light purple', 'dark purple', 'other purple'),
    'violet': ('purple', 'dark purple', 'light purple'),
    'gold': ('gold',),
    'silver': ('silver',),
    'turquoise': ('turquoise', 'light turquoise', 'dark turquoise', 'other turquoise'),
    'teal': ('turquoise', 'dark turquoise'),
    'bronze': ('bronze/copper',),
    'copper': ('bronze/copper',),
    'tomato': ('red', 'dark red'),
    'cherry': ('red', 'dark red'),
    'burgundy': ('dark red',),
    'maroon': ('dark red',),
    'wine': ('dark red',),
    'olive': ('greenish khaki', 'dark green'),
    'mint': ('light green',),
    'lavender': ('light purple',),
    'lilac': ('light purple',),
    'blush': ('light pink', 'pink'),
    'rose': ('pink', 'light pink'),
    'coral': ('light orange', 'orange'),
    'mustard': ('yellow', 'dark yellow'),
    'snow': ('white',),
    'forest': ('dark green',),
    'ocean': ('dark blue', 'blue'),
    'sky': ('light blue',),
}

EXACT_COLORS = {
    'black', 'white', 'dark blue', 'light pink', 'grey', 'light beige', 'blue',
    'red', 'light blue', 'greenish khaki', 'dark grey', 'off white', 'beige',
    'dark red', 'dark green', 'light grey', 'pink', 'yellow', 'light orange',
    'yellowish brown', 'gold', 'dark beige', 'light turquoise', 'light yellow',
    'dark orange', 'green', 'dark pink', 'orange', 'other pink', 'silver',
    'light green', 'dark yellow', 'light purple', 'dark turquoise', 'turquoise',
    'dark purple', 'light red', 'greyish beige', 'other yellow', 'purple',
    'other orange', 'other green', 'other red', 'bronze/copper', 'other blue',
    'other purple', 'transparent', 'other', 'unknown', 'other turquoise',
}

BAG_TYPES = ('Bag', 'Shoulder bag', 'Tote bag', 'Cross-body bag')
HAND_BAGS = BAG_TYPES
SHOE_TYPES = (
    'Sneakers', 'Boots', 'Sandals', 'Heels', 'Pumps', 'Flat shoe', 'Flat shoes',
    'Ballerinas', 'Slippers', 'Wedge', 'Other shoe', 'Bootie', 'Moccasins',
    'Heeled sandals', 'Pre-walkers', 'Flip flop',
)
JEWELRY = ('Necklace', 'Earring', 'Earrings', 'Bracelet', 'Ring')
HEELS = ('Heels', 'Pumps', 'Heeled sandals', 'Wedge', 'Ballerinas')
HATS = ('Hat/beanie', 'Beanie', 'Cap', 'Cap/peaked', 'Hat/brim', 'Straw hat', 'Felt hat', 'Bucket hat')

# phrase -> tuple of product_type names, or a sentinel handled below
def _types(*names):
    return tuple(names)

TYPE_ALIASES = {
    't shirts': _types('T-shirt'),
    't shirt': _types('T-shirt'),
    'tee shirts': _types('T-shirt'),
    'tee shirt': _types('T-shirt'),
    'tshirt': _types('T-shirt'),
    'tshirts': _types('T-shirt'),
    'tees': _types('T-shirt'),
    'tee': _types('T-shirt'),
    'polo shirts': _types('Polo shirt'),
    'polo shirt': _types('Polo shirt'),
    'polo': _types('Polo shirt'),
    'vest tops': _types('Vest top'),
    'vest top': _types('Vest top'),
    'vests': _types('Vest top'),
    'vest': _types('Vest top'),
    'jeans': ('JEANS',),
    'jean': ('JEANS',),
    'dresses': _types('Dress'),
    'dress': _types('Dress'),
    'gowns': _types('Dress'),
    'gown': _types('Dress'),
    'skirts': _types('Skirt'),
    'skirt': _types('Skirt'),
    'trousers': _types('Trousers'),
    'trouser': _types('Trousers'),
    'pants': _types('Trousers'),
    'slacks': _types('Trousers'),
    'chinos': _types('Trousers'),
    'joggers': _types('Trousers'),
    'sweatpants': _types('Trousers'),
    'khakis': _types('Trousers'),
    'hoodies': _types('Hoodie'),
    'hoodie': _types('Hoodie'),
    'sweatshirts': _types('Hoodie'),
    'sweatshirt': _types('Hoodie'),
    'sweaters': _types('Sweater'),
    'sweater': _types('Sweater'),
    'jumpers': _types('Sweater'),
    'jumper': _types('Sweater'),
    'pullovers': _types('Sweater'),
    'pullover': _types('Sweater'),
    'knits': _types('Sweater'),
    'cardigans': _types('Cardigan'),
    'cardigan': _types('Cardigan'),
    'jackets': _types('Jacket'),
    'jacket': _types('Jacket'),
    'coats': _types('Coat'),
    'coat': _types('Coat'),
    'overcoats': _types('Coat'),
    'overcoat': _types('Coat'),
    'blazers': _types('Blazer'),
    'blazer': _types('Blazer'),
    'blouses': _types('Blouse'),
    'blouse': _types('Blouse'),
    'shirts': _types('Shirt'),
    'shirt': _types('Shirt'),
    'shorts': _types('Shorts'),
    'leggings': _types('Leggings/Tights'),
    'legging': _types('Leggings/Tights'),
    'tights': _types('Leggings/Tights'),
    'sneakers': _types('Sneakers'),
    'sneaker': _types('Sneakers'),
    'trainers': _types('Sneakers'),
    'trainer': _types('Sneakers'),
    'kicks': _types('Sneakers'),
    'boots': _types('Boots'),
    'boot': _types('Boots'),
    'sandals': _types('Sandals'),
    'sandal': _types('Sandals'),
    'heels': HEELS,
    'heel': HEELS,
    'stilettos': HEELS,
    'stiletto': HEELS,
    'pumps': _types('Pumps'),
    'pump': _types('Pumps'),
    'flats': _types('Flat shoe', 'Flat shoes', 'Ballerinas'),
    'ballerinas': _types('Ballerinas'),
    'slippers': _types('Slippers'),
    'shoes': SHOE_TYPES,
    'shoe': SHOE_TYPES,
    'footwear': SHOE_TYPES,
    'handbags': HAND_BAGS,
    'handbag': HAND_BAGS,
    'purses': HAND_BAGS,
    'purse': HAND_BAGS,
    'bags': HAND_BAGS,
    'bag': HAND_BAGS,
    'tote': _types('Tote bag'),
    'totes': _types('Tote bag'),
    'backpacks': _types('Backpack'),
    'backpack': _types('Backpack'),
    'earrings': _types('Earring', 'Earrings'),
    'earring': _types('Earring', 'Earrings'),
    'necklaces': _types('Necklace'),
    'necklace': _types('Necklace'),
    'bracelets': _types('Bracelet'),
    'bracelet': _types('Bracelet'),
    'rings': _types('Ring'),
    'ring': _types('Ring'),
    'jewelry': JEWELRY,
    'jewellery': JEWELRY,
    'scarves': _types('Scarf'),
    'scarf': _types('Scarf'),
    'belts': _types('Belt'),
    'belt': _types('Belt'),
    'hats': HATS,
    'hat': HATS,
    'beanies': _types('Beanie', 'Hat/beanie'),
    'beanie': _types('Beanie', 'Hat/beanie'),
    'caps': _types('Cap', 'Cap/peaked'),
    'cap': _types('Cap', 'Cap/peaked'),
    'sunglasses': _types('Sunglasses'),
    'sunnies': _types('Sunglasses'),
    'watches': _types('Watch'),
    'watch': _types('Watch'),
    'bras': _types('Bra'),
    'bra': _types('Bra'),
    'socks': _types('Socks'),
    'sock': _types('Socks'),
    'swimsuits': _types('Swimsuit'),
    'swimsuit': _types('Swimsuit'),
    'bikinis': _types('Bikini top', 'Swimwear bottom', 'Swimwear set'),
    'bikini': _types('Bikini top', 'Swimwear bottom', 'Swimwear set'),
    'swimwear': _types('Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set', 'Swimwear top'),
    'pyjamas': _types('Pyjama set', 'Pyjama bottom', 'Pyjama jumpsuit/playsuit'),
    'pyjama': _types('Pyjama set', 'Pyjama bottom', 'Pyjama jumpsuit/playsuit'),
    'pajamas': _types('Pyjama set', 'Pyjama bottom', 'Pyjama jumpsuit/playsuit'),
    'pajama': _types('Pyjama set', 'Pyjama bottom', 'Pyjama jumpsuit/playsuit'),
    'pjs': _types('Pyjama set'),
    'jumpsuits': _types('Jumpsuit/Playsuit'),
    'jumpsuit': _types('Jumpsuit/Playsuit'),
    'playsuits': _types('Jumpsuit/Playsuit'),
    'playsuit': _types('Jumpsuit/Playsuit'),
    'bodysuits': _types('Bodysuit'),
    'bodysuit': _types('Bodysuit'),
    'underwear': _types('Underwear bottom', 'Underwear set', 'Bra'),
    'panties': _types('Underwear bottom'),
    'boxers': _types('Underwear bottom'),
    'briefs': _types('Underwear bottom'),
    'ties': _types('Tie'),
    'tie': _types('Tie'),
    'gloves': _types('Gloves'),
    'glove': _types('Gloves'),
    'wallets': _types('Wallet'),
    'wallet': _types('Wallet'),
    'coats': _types('Coat'),
    'nightwear': _types('Pyjama set', 'Night gown', 'Robe'),
    'nightgown': _types('Night gown'),
    'robe': _types('Robe'),
    'robes': _types('Robe'),
    'costumes': _types('Costumes'),
    'costume': _types('Costumes'),
    'dungarees': _types('Dungarees'),
    'overalls': _types('Dungarees'),
    'waistcoat': _types('Tailored Waistcoat'),
    'waistcoats': _types('Tailored Waistcoat'),
    'accessories': _types('Other accessories', 'Scarf', 'Belt', 'Hat/beanie', 'Cap/peaked', 'Sunglasses', 'Necklace', 'Earring', 'Bag', 'Gloves'),
    'accessory': _types('Other accessories', 'Scarf', 'Belt', 'Hat/beanie', 'Necklace', 'Earring', 'Bag'),
}

OCCASIONS = {
    'lazy sunday': _types('Hoodie', 'Sweater', 'Leggings/Tights', 'Pyjama set', 'Cardigan', 'Trousers'),
    'lazy day': _types('Hoodie', 'Sweater', 'Leggings/Tights', 'Pyjama set', 'Cardigan'),
    'date night': _types('Dress', 'Heels', 'Blouse', 'Blazer', 'Skirt', 'Shirt'),
    'night out': _types('Dress', 'Heels', 'Blouse', 'Skirt', 'Shirt'),
    'loungewear': _types('Hoodie', 'Sweater', 'Leggings/Tights', 'Pyjama set', 'Cardigan'),
    'wedding': _types('Dress', 'Blazer', 'Heels', 'Pumps', 'Shirt', 'Blouse', 'Skirt', 'Necklace'),
    'bridal': _types('Dress', 'Heels', 'Pumps', 'Necklace', 'Blouse'),
    'party': _types('Dress', 'Heels', 'Blouse', 'Skirt', 'Shirt'),
    'dinner': _types('Dress', 'Blazer', 'Heels', 'Blouse', 'Shirt', 'Skirt'),
    'evening': _types('Dress', 'Heels', 'Blazer', 'Blouse', 'Skirt'),
    'formal': _types('Blazer', 'Shirt', 'Trousers', 'Dress', 'Blouse', 'Heels', 'Pumps'),
    'office': _types('Blazer', 'Shirt', 'Trousers', 'Blouse', 'Dress'),
    'workwear': _types('Blazer', 'Shirt', 'Trousers', 'Blouse'),
    'interview': _types('Blazer', 'Shirt', 'Trousers', 'Blouse', 'Dress'),
    'workout': _types('Sneakers', 'Leggings/Tights', 'T-shirt', 'Shorts', 'Hoodie'),
    'gym': _types('Sneakers', 'Leggings/Tights', 'T-shirt', 'Shorts', 'Hoodie'),
    'running': _types('Sneakers', 'T-shirt', 'Shorts', 'Leggings/Tights'),
    'athletic': _types('Sneakers', 'Leggings/Tights', 'T-shirt', 'Shorts', 'Hoodie'),
    'sportswear': _types('Sneakers', 'Leggings/Tights', 'T-shirt', 'Shorts', 'Hoodie'),
    'sport': _types('Sneakers', 'Leggings/Tights', 'T-shirt', 'Shorts', 'Hoodie'),
    'beach': _types('Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set', 'Sandals', 'Shorts'),
    'swim': _types('Swimsuit', 'Bikini top', 'Swimwear bottom', 'Swimwear set'),
    'rainy': _types('Jacket', 'Coat', 'Boots'),
    'rain': _types('Jacket', 'Coat', 'Boots'),
    'winter': _types('Sweater', 'Coat', 'Jacket', 'Hoodie', 'Cardigan', 'Boots', 'Scarf'),
    'cold': _types('Sweater', 'Coat', 'Jacket', 'Hoodie', 'Cardigan'),
    'summer': _types('Dress', 'Shorts', 'T-shirt', 'Sandals', 'Skirt', 'Vest top'),
    'lounge': _types('Hoodie', 'Sweater', 'Leggings/Tights', 'Pyjama set', 'Cardigan'),
    'sleep': _types('Pyjama set', 'Pyjama bottom', 'Night gown', 'Robe'),
    'sleepwear': _types('Pyjama set', 'Pyjama bottom', 'Night gown', 'Robe'),
    'vacation': _types('Dress', 'Shorts', 'Sandals', 'T-shirt', 'Swimsuit'),
    'holiday': _types('Dress', 'Shorts', 'Sandals', 'Shirt', 'Blouse'),
    'cozy': _types('Hoodie', 'Sweater', 'Cardigan', 'Pyjama set'),
}

OCCASIONS['lazy'] = OCCASIONS['loungewear']

# Aliases that are broader than the shopper's word. Keep the word as a text constraint.
TEXT_CONSTRAINTS = {
    'chinos': 'chinos',
    'chino': 'chinos',
    'joggers': 'joggers',
    'jogger': 'joggers',
    'sweatpants': 'sweatpants',
    'khakis': 'khakis',
    'trainers': 'trainers',
    'trainer': 'trainers',
    'gown': 'gown',
    'gowns': 'gown',
    'pullover': 'pullover',
    'pullovers': 'pullover',
    'jumper': 'jumper',
    'jumpers': 'jumper',
    'sweatshirt': 'sweatshirt',
    'sweatshirts': 'sweatshirt',
}

PATTERN_ALIASES = {
    'polka dots': 'dot',
    'polka dot': 'dot',
    'polka': 'dot',
    'dotted': 'dot',
    'dots': 'dot',
    'striped': 'stripe',
    'stripes': 'stripe',
    'stripe': 'stripe',
    'checked': 'check',
    'checkered': 'check',
    'plaid': 'check',
    'checks': 'check',
    'lace': 'lace',
    'denim': 'denim',
    'glitter': 'glittering/metallic',
    'glittery': 'glittering/metallic',
    'sequins': 'sequin',
    'sequin': 'sequin',
    'floral print': 'all over pattern',
    'embroidered': 'embroidery',
    'embroidery': 'embroidery',
    'camouflage': 'all over pattern',
    'mesh': 'mesh',
    'metallic': 'metallic',
}

SECTION_ALIASES = {
    'plus size': 'h&m+',
    'plus-size': 'h&m+',
    'maternity': 'mama',
    'pregnant': 'mama',
    'pregnancy': 'mama',
}

WOMEN_RE = re.compile(r'\b(?:womens?|women|woman|ladies|lady|female)\b')
MEN_RE = re.compile(r'\b(?:mens?|men|man|male|guys?|guy)\b')
BABY_RE = re.compile(r'\b(?:baby|infant|newborn|toddler)\b')
KIDS_RE = re.compile(r'\b(?:kids?|children|child)\b')
GIRL_RE = re.compile(r'\b(?:girls?)\b')
BOY_RE = re.compile(r'\b(?:boys?)\b')

YOUTH_AUDIENCES = (
    'children sizes 92-140',
    'children sizes 134-170',
    'children accessories, swimwear',
    'baby sizes 50-98',
)
MEN_AUDIENCES = ('menswear', 'divided')
WOMEN_EXCLUDE = ('menswear',) + YOUTH_AUDIENCES

RATING_RE = re.compile(
    r'\b(?:(?:at least|over|above|minimum)\s+)?(\d(?:\.\d+)?)\s*\+?\s*(?:star|stars)(?:\s+rating)?'
    r'|\brated\s+(?:at least\s+|over\s+|above\s+)?(\d(?:\.\d+)?)'
    r'|\brating\s+(?:of\s+|at least\s+)?(\d(?:\.\d+)?)'
)
BETWEEN_RE = re.compile(
    r'\bbetween\s+(?:(?:inr|rs|rupees)\s*)?(\d+(?:\.\d+)?)\s+and\s+(?:(?:inr|rs|rupees)\s*)?(\d+(?:\.\d+)?)'
)
FROM_TO_RE = re.compile(
    r'\bfrom\s+(?:(?:inr|rs|rupees)\s*)?(\d+(?:\.\d+)?)\s+to\s+(?:(?:inr|rs|rupees)\s*)?(\d+(?:\.\d+)?)'
)
UNDER_RE = re.compile(
    r'\b(?:under|below|less than|up to|upto|within|at most|max(?:imum)?(?:\s+price)?|budget(?:\s+of)?)\s+'
    r'(?:(?:inr|rs|rupees)\s*)?(\d+(?:\.\d+)?)(?!\s*(?:star|stars|rating))'
)
OVER_RE = re.compile(
    r'\b(?:over|above|more than|at least|min(?:imum)?(?:\s+price)?|from)\s+'
    r'(?:(?:inr|rs|rupees)\s*)?(\d+(?:\.\d+)?)(?!\s*(?:star|stars|rating))'
)
BARE_RE = re.compile(r'\b(?:inr|rs|rupees)\s*(\d+(?:\.\d+)?)')

COMPLEMENT_RE = re.compile(
    r'^(?P<head>.*?)\b(?:'
    r'with\s+(?:a\s+|an\s+|the\s+)?(?:matching|complementary|coordinating)\s+'
    r'|with\s+(?:a|an|the)\s+'
    r'|plus\s+(?:a\s+|an\s+|the\s+)?(?:matching\s+)?'
    r'|to\s+go\s+with\s+(?:a\s+|an\s+|the\s+)?'
    r'|that\s+goes\s+with\s+(?:a\s+|an\s+|the\s+)?'
    r'|goes\s+with\s+(?:a\s+|an\s+|the\s+)?'
    r'|paired\s+with\s+(?:a\s+|an\s+|the\s+)?'
    r'|complete\s+the\s+(?:look|outfit)\s+with\s+(?:a\s+|an\s+|the\s+)?'
    r'|along\s+with\s+(?:a\s+|an\s+|the\s+)?'
    r'|and\s+(?:a\s+|an\s+|the\s+)?matching\s+'
    r')(?P<tail>.+)$'
)


def _compile(phrases):
    ordered = sorted(set(phrases), key=len, reverse=True)
    if not ordered:
        return re.compile(r'(?!x)x')
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in ordered) + r')\b')


TYPE_RE = _compile(TYPE_ALIASES)
COLOR_RE = _compile(list(EXACT_COLORS) + list(COLOR_GROUPS))
OCCASION_RE = _compile(OCCASIONS)
PATTERN_RE = _compile(PATTERN_ALIASES)
SECTION_RE = _compile(SECTION_ALIASES)


@dataclass
class Choice:
    types: tuple = ()
    jeans: bool = False
    colors: tuple = ()
    audiences: tuple = ()
    exclude_audiences: tuple = ()
    sections: tuple = ()
    patterns: tuple = ()
    min_price: float | None = None
    max_price: float | None = None
    min_rating: float | None = None
    required_tokens: tuple = ()
    boost_tokens: tuple = ()
    occasion_types: tuple = ()
    youth: bool = False
    text: str = ''


@dataclass
class Intent:
    abstain: bool = False
    ood: bool = False
    choices: tuple = ()
    complement: Choice | None = None
    price_each: bool = False
    raw: str = ''


def normalize(text):
    text = text.casefold().replace('₹', ' ').replace("'", '')
    text = re.sub(r'[-_/]+', ' ', text)
    text = re.sub(r'[^a-z0-9\s&+]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _blank(text, spans):
    if not spans:
        return text
    chars = list(text)
    for start, end in spans:
        for i in range(max(0, start), min(len(chars), end)):
            chars[i] = ' '
    return ''.join(chars)


def _collect_prices(text):
    spans = []
    bounds = []

    def take(regex, kind):
        for match in regex.finditer(text):
            if any(not (match.end() <= s or match.start() >= e) for s, e in spans):
                continue
            spans.append((match.start(), match.end()))
            if kind == 'between':
                lo, hi = float(match.group(1)), float(match.group(2))
                if lo > hi:
                    lo, hi = hi, lo
                bounds.append((match.start(), lo, hi))
            elif kind == 'under':
                bounds.append((match.start(), None, float(match.group(1))))
            elif kind == 'over':
                bounds.append((match.start(), float(match.group(1)), None))
            else:
                bounds.append((match.start(), None, float(match.group(1))))

    take(BETWEEN_RE, 'between')
    take(FROM_TO_RE, 'between')
    take(UNDER_RE, 'under')
    take(OVER_RE, 'over')
    take(BARE_RE, 'bare')
    return spans, bounds


def _rating(text):
    spans = []
    value = None
    for match in RATING_RE.finditer(text):
        spans.append((match.start(), match.end()))
        raw = next(g for g in match.groups() if g)
        number = float(raw)
        if 1 <= number <= 5:
            value = number if value is None else max(value, number)
    return value, spans


def _phrases(regex, table, text):
    found = []
    spans = []
    for match in regex.finditer(text):
        phrase = match.group(0)
        payload = table.get(phrase)
        if payload is None:
            continue
        found.append(payload)
        spans.append((match.start(), match.end()))
    return found, spans


def _colors_from(text):
    colors = []
    spans = []
    exact_only = {'black', 'white', 'gold', 'silver'}
    modifiers = ('light ', 'dark ', 'other ', 'off ', 'greenish ', 'greyish ', 'yellowish ')
    for match in COLOR_RE.finditer(text):
        phrase = match.group(0)
        if phrase in exact_only or (phrase in EXACT_COLORS and phrase.startswith(modifiers)):
            colors.append(phrase)
        elif phrase in COLOR_GROUPS:
            colors.extend(COLOR_GROUPS[phrase])
        elif phrase in EXACT_COLORS:
            colors.append(phrase)
        spans.append((match.start(), match.end()))
    # Unique, stable.
    seen = set()
    ordered = []
    for color in colors:
        if color not in seen:
            seen.add(color)
            ordered.append(color)
    return tuple(ordered), spans


def _types_from(text):
    types = []
    jeans = False
    spans = []
    for match in TYPE_RE.finditer(text):
        payload = TYPE_ALIASES[match.group(0)]
        spans.append((match.start(), match.end()))
        if payload == ('JEANS',):
            jeans = True
            continue
        for name in payload:
            if name not in types:
                types.append(name)
    return tuple(types), jeans, spans


def _audience_flags(text):
    women = WOMEN_RE.search(text) is not None
    men = MEN_RE.search(text) is not None
    baby = BABY_RE.search(text) is not None
    kids = KIDS_RE.search(text) is not None
    girl = GIRL_RE.search(text) is not None
    boy = BOY_RE.search(text) is not None
    return women, men, baby, kids, girl, boy


def _apply_audience(choice, text):
    women, men, baby, kids, girl, boy = _audience_flags(text)
    sections = list(choice.sections)
    audiences = list(choice.audiences)
    exclude = list(choice.exclude_audiences)
    youth = baby or kids or girl or boy
    both_genders = women and men
    if both_genders:
        pass
    elif baby:
        audiences = ['baby sizes 50-98']
    elif kids and not (girl or boy):
        audiences = ['children sizes 92-140', 'children sizes 134-170', 'children accessories, swimwear']
    elif boy and not men:
        sections.extend(['kids boy', 'young boy', 'baby boy', 'boys underwear & basics'])
        youth = True
    elif girl and not women:
        sections.extend(['kids girl', 'young girl', 'baby girl', 'girls underwear & basics'])
        youth = True
    elif men:
        audiences = list(MEN_AUDIENCES)
    elif women and not youth:
        exclude.extend(WOMEN_EXCLUDE)
    # unique
    def uniq(values):
        seen = set()
        out = []
        for value in values:
            if value not in seen:
                seen.add(value)
                out.append(value)
        return tuple(out)
    choice.audiences = uniq(audiences)
    choice.exclude_audiences = uniq(exclude)
    choice.sections = uniq(sections)
    choice.youth = youth
    return choice


def _leftover_tokens(text):
    tokens = re.findall(r'\w+', text)
    required = []
    boost = []
    for token in tokens:
        if token in STOP or token.isdigit() or len(token) <= 1:
            continue
        if token in ADJECTIVES:
            boost.append(token)
            continue
        if token in OOD:
            continue
        required.append(token)
    return tuple(dict.fromkeys(required)), tuple(dict.fromkeys(boost))


def parse_choice(text, price_bounds, rating):
    occasions, occasion_spans = _phrases(OCCASION_RE, OCCASIONS, text)
    types, jeans, type_spans = _types_from(text)
    colors, color_spans = _colors_from(text)
    patterns, pattern_spans = _phrases(PATTERN_RE, PATTERN_ALIASES, text)
    sections, section_spans = _phrases(SECTION_RE, SECTION_ALIASES, text)
    blanked = _blank(text, occasion_spans + type_spans + color_spans + pattern_spans + section_spans)
    required, boost = _leftover_tokens(blanked)
    required = list(required)
    for match in TYPE_RE.finditer(text):
        extra = TEXT_CONSTRAINTS.get(match.group(0))
        if extra and extra not in required:
            required.append(extra)
    required = tuple(required)
    occasion_types = []
    for payload in occasions:
        if isinstance(payload, tuple):
            for name in payload:
                if name not in occasion_types and name != 'JEANS':
                    occasion_types.append(name)
    # A named product type beats a vague occasion list.
    specific = bool(types or jeans)
    lo = hi = None
    for _, bound_lo, bound_hi in price_bounds:
        if bound_lo is not None:
            lo = bound_lo if lo is None else max(lo, bound_lo)
        if bound_hi is not None:
            hi = bound_hi if hi is None else min(hi, bound_hi)
    if specific:
        extra = [token for token in re.findall(r'\w+', text) if token in OCCASIONS]
        boost = list(boost) + extra
    choice = Choice(
        types=types,
        jeans=jeans,
        colors=colors,
        sections=tuple(dict.fromkeys(list(sections))),
        patterns=tuple(dict.fromkeys(patterns)),
        min_price=lo,
        max_price=hi,
        min_rating=rating,
        required_tokens=required,
        boost_tokens=tuple(dict.fromkeys(boost)),
        occasion_types=() if specific else tuple(occasion_types),
        text=text.strip(),
    )
    return _apply_audience(choice, text)


def _segment_bounds(segment_start, segment_end, bounds):
    own = []
    for pos, lo, hi in bounds:
        if segment_start <= pos < segment_end:
            own.append((pos, lo, hi))
    return own


def _has_type(text):
    return TYPE_RE.search(text) is not None


def _mixed_ranges(text):
    cuts = [0]
    for match in re.finditer(r'\band\b|\bor\b|,', text):
        cuts.append(match.start())
        cuts.append(match.end())
    cuts.append(len(text))
    ranges = []
    for start, end in zip(cuts[0::2], cuts[1::2]):
        segment = text[start:end].strip()
        if segment:
            ranges.append((start, end, text[start:end]))
    if len(ranges) >= 2 and all(_has_type(segment) for _, _, segment in ranges):
        return ranges
    return None


def _with_global_prices(choice, bounds):
    if choice is None or not bounds:
        return choice
    lo, hi = choice.min_price, choice.max_price
    for _, bound_lo, bound_hi in bounds:
        if bound_lo is not None:
            lo = bound_lo if lo is None else max(lo, bound_lo)
        if bound_hi is not None:
            hi = bound_hi if hi is None else min(hi, bound_hi)
    if lo == choice.min_price and hi == choice.max_price:
        return choice
    return Choice(**{**choice.__dict__, 'min_price': lo, 'max_price': hi})


def parse_intent(query, correct=None):
    raw_norm = normalize(query)
    if not raw_norm:
        return Intent(raw=raw_norm)
    ood = any(token in OOD for token in raw_norm.split())
    text = raw_norm
    if correct is not None:
        text = ' '.join(correct(token) for token in text.split())
        text = re.sub(r'\s+', ' ', text).strip()
    rating, rating_spans = _rating(text)
    text = _blank(text, rating_spans)
    price_each = re.search(r'\beach\b', text) is not None
    price_spans, price_bounds = _collect_prices(text)
    # Keep character indexes stable so prices stay attached to the right clause.
    detectable = _blank(text, price_spans)

    complement = None
    head = detectable
    head_start = 0
    head_end = len(detectable)
    match = COMPLEMENT_RE.match(detectable)
    head_has_request = bool(match and match.group('head').strip())
    if match and _has_type(match.group('tail')) and head_has_request:
        head_start = match.start('head')
        head_end = match.start('tail')
        head = detectable[head_start:head_end]
        complement = parse_choice(
            detectable[match.start('tail'):match.end('tail')],
            _segment_bounds(match.start('tail'), match.end('tail'), price_bounds),
            None)

    mixed = _mixed_ranges(head)
    if mixed:
        choices = []
        covered = []
        for start, end, segment in mixed:
            absolute_start = head_start + start
            absolute_end = head_start + end
            local = _segment_bounds(absolute_start, absolute_end, price_bounds)
            covered.extend(local)
            choices.append(parse_choice(segment, local, rating))
        outside = [bound for bound in price_bounds if bound not in covered and not (
            complement is not None and head_end <= bound[0])]
        if outside:
            choices = [_with_global_prices(choice, outside) if choice.min_price is None and choice.max_price is None else choice
                       for choice in choices]
    else:
        choices = [parse_choice(head, _segment_bounds(head_start, head_end, price_bounds), rating)]

    # One budget beside several choices applies to every primary choice.
    # A single budget in front of a complement stays on the primary item.
    if len(price_bounds) == 1 and complement is None:
        choices = [_with_global_prices(choice, price_bounds) for choice in choices]

    if price_each and price_bounds:
        choices = [_with_global_prices(choice, price_bounds) for choice in choices]
        complement = _with_global_prices(complement, price_bounds)

    structured = any(
        c.types or c.jeans or c.colors or c.occasion_types or c.audiences or c.sections or c.patterns
        for c in choices)
    abstain = bool(ood and not structured and complement is None)
    return Intent(
        abstain=abstain, ood=ood, choices=tuple(choices), complement=complement,
        price_each=price_each, raw=text)


def protected_terms():
    words = set(STOP) | set(ADJECTIVES) | set(OOD)
    for table in (TYPE_ALIASES, COLOR_GROUPS, OCCASIONS, PATTERN_ALIASES, SECTION_ALIASES):
        for phrase in table:
            words.update(phrase.split())
    words.update(EXACT_COLORS)
    return words
