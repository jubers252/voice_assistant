
import requests
from pprint import pprint
import json
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List, Set
import re

# --- Configuration ---
OX_LABS_ENDPOINT = 'https://realtime.oxylabs.io/v1/queries'
OX_LABS_AUTH = ('juber_7pRAM', 'LSfU3YuuA8xM_AS')
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


FIRST_ORG_PRODUCT_INFO = 'first_organic_product_info.json'


# --- Helpers: Oxylabs parsed result handling ---
def load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def call_oxylabs_search(query: str, domain: str = 'in', locale: str = 'en-in', parse: bool = True) -> Dict[str, Any]:
    payload = {
        'source': 'amazon_search',
        'query': query,
        'domain': domain,
        'locale': locale,
        'parse': parse,
    }
    resp = requests.post(OX_LABS_ENDPOINT, auth=OX_LABS_AUTH, json=payload)
    resp.raise_for_status()
    return resp.json()


def extract_first_organic(result_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a dict with 'asin', 'url' (full) and 'raw' for the first organic result if present."""
    try:
        results = result_json.get('results', [])
        if not results:
            return None
        content = results[0].get('content', {})
        organic = content.get('results', {}).get('organic', [])
        if not organic:
            return None
        first = organic[0]
        asin = first.get('asin')
        url_path = first.get('url')
        full_url = url_path if url_path and url_path.startswith('http') else (f"https://www.amazon.in{url_path}" if url_path else None)
        return {'asin': asin, 'url': full_url, 'raw': first}
    except Exception:
        return None


def extract_top_organic_items(result_json: Dict[str, Any], limit: int = 5) -> list:
    """Return up to `limit` organic items (each with asin, url, raw) from an Oxylabs result JSON."""
    try:
        results = result_json.get('results', [])
        if not results:
            return []
        content = results[0].get('content', {})
        organic = content.get('results', {}).get('organic', [])
        items = []
        for raw in organic[:limit]:
            asin = raw.get('asin')
            url_path = raw.get('url')
            full_url = url_path if url_path and url_path.startswith('http') else (f"https://www.amazon.in{url_path}" if url_path else None)
            items.append({'asin': asin, 'url': full_url, 'raw': raw})
        return items
    except Exception:
        return []


def extract_description_from_raw(raw: Dict[str, Any]) -> Optional[str]:
    """Try to extract a description/snippet from a single `raw` organic entry."""
    if not isinstance(raw, dict):
        return None
    for k in ('excerpt', 'snippet', 'description', 'summary'):
        v = raw.get(k)
        if v:
            if isinstance(v, list):
                return '\n'.join([str(x) for x in v])
            return str(v)
    return None


# --- Helpers: product page parsing ---
def safe_select_text(soup: BeautifulSoup, selector: str) -> Optional[str]:
    node = soup.select_one(selector)
    if node:
        text = node.get_text().strip()
        return text if text else None
    return None


def fetch_product_page(product_url: str) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(product_url, headers=DEFAULT_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        return BeautifulSoup(resp.content, 'html.parser')
    except Exception:
        return None


def extract_description_from_soup(soup: BeautifulSoup) -> Optional[str]:
    # Primary product description container
    desc = None
    desc = safe_select_text(soup, '#productDescription') or safe_select_text(soup, '#aplus .a-section') or safe_select_text(soup, '#aplus')
    if desc:
        return desc
    # Fallback to feature bullets
    bullets = [b.get_text().strip() for b in soup.select('#feature-bullets ul li') if b.get_text().strip()]
    if bullets:
        return '\n'.join(bullets)
    return None


# --- Helpers: bank-offer extraction utilities (module-level for reuse) ---
def normalize_offer(text: str) -> str:
    return re.sub(r"\s+", ' ', text).strip()


def clean_noise(text: str) -> str:
    text = re.sub(r'\b\d+\s+offers?\b', '', text, flags=re.I)
    text = re.sub(r'\b\d+\s+offer\b', '', text, flags=re.I)
    return text.strip()


def is_offer_text(text: str) -> bool:
    if not text:
        return False
    s = text.strip()
    if len(s) < 10 or len(s) > 400:
        return False
    if re.search(r'(About Amazon|Careers|Facebook|Twitter|Instagram|Sell on Amazon|AbeBooks|Amazon Web Services|Audible|IMDb|Prime Music|Conditions of Use|Privacy Notice|Interest-Based Ads|Your Account|Returns Centre)', s, flags=re.I):
        return False
    if re.search(r'\d+ out of \d+ stars|Get it by|M\.R\.P|Sale Price|Limited time deal|Save \u20B9', s, flags=re.I):
        return False
    offer_keywords = re.compile(r'\b(?:bank|emi|cashback|cash back|no cost emi|no-cost emi|discount|exchange|offer|instant|\u20B9|rs\.?|rupee|%|up to|upto|coupon|save|savings|partner)\b', flags=re.I)
    bank_names = re.compile(r'\b(?:sbi|hdfc|icici|axis|kotak|idbi|citi|paytm|yes bank|indusind|standard chartered|hdfc bank|icici bank|axis bank)\b', flags=re.I)
    return bool(offer_keywords.search(s) or bank_names.search(s))


def add_candidate_to_list(text: str, offers: List[str], seen: Set[str]) -> None:
    if not text:
        return
    t = normalize_offer(text)
    if not t or t.lower() == 'bank offer':
        return
    t = clean_noise(t)
    if not is_offer_text(t):
        return
    candidate = 'Bank Offer: ' + t if not t.lower().startswith('bank offer') else t
    if candidate not in seen:
        seen.add(candidate)
        offers.append(candidate)


def extract_from_block(block, offers: List[str], seen: Set[str]) -> None:
    raw = block.get_text(separator='\n', strip=True)
    lis = block.find_all('li')
    if lis:
        for li in lis:
            li_text = li.get_text(separator=' ', strip=True)
            if 'Bank Offer' in li_text:
                parts = re.split(r'(?i)Bank Offer[:\-\s]*', li_text)
                for part in parts[1:]:
                    add_candidate_to_list(part, offers, seen)
            else:
                if 'Bank Offer' in raw:
                    add_candidate_to_list(li_text, offers, seen)
        return
    parts = re.split(r'(?i)Bank Offer[:\-\s]*', raw)
    if len(parts) > 1:
        for part in parts[1:]:
            piece = part.split('\n', 1)[0]
            add_candidate_to_list(piece, offers, seen)
        return
    m = re.search(r'Bank Offer[:\-\s]*([\s\S]+)', raw, flags=re.I)
    if m:
        add_candidate_to_list(m.group(1), offers, seen)
    else:
        if 'Bank Offer' in raw and len(raw) > 20:
            add_candidate_to_list(raw, offers, seen)


def extract_bank_offers_from_soup(soup: BeautifulSoup) -> Optional[list]:
    """Extract visible 'Bank Offer' texts from an Amazon product page soup.

    Heuristic approach:
    - Find strings that contain 'Bank Offer'.
    - For each match, inspect ancestors and nearby siblings to capture the full offer
      (e.g. "Bank Offer 10% instant discount on XYZ card").
    - Also scan a few common promotion selectors and extract longer text.
    - Skip entries that are only the literal 'Bank Offer' with no details.

    Returns a list of offer strings (empty list if none), or None on unexpected errors.
    """
    # Use module-level helper functions defined above for maintainability

    try:
        offers = []
        seen = set()

        # focused pass: look for nodes containing the phrase and process surrounding block
        for node in soup.find_all(string=lambda s: s and 'Bank Offer' in s):
            ancestor = node.parent
            block = ancestor
            for _ in range(4):
                txt = normalize_offer(block.get_text(separator='\n', strip=True))
                if len(txt) > 20 and 'Bank Offer' in txt:
                    break
                if block.parent is None:
                    break
                block = block.parent
            extract_from_block(block, offers, seen)

        # broader passes: ul/ol lists, label-following siblings, and global visible text scan
        for ul in soup.find_all(['ul', 'ol']):
            parent = ul.find_parent()
            parent_text = parent.get_text(separator=' ', strip=True) if parent else ''
            prev = ul.find_previous(string=lambda s: s and 'bank offer' in s.lower())
            next_label = ul.find_previous()
            has_label_nearby = bool(prev) or ('bank offer' in parent_text.lower()) or (isinstance(next_label, str) and 'bank offer' in next_label.lower())
            if has_label_nearby:
                for li in ul.find_all('li'):
                    add_candidate_to_list(li.get_text(separator=' ', strip=True), offers, seen)

        for node in soup.find_all(string=lambda s: s and 'bank offer' in s.lower()):
            el = node.parent
            count = 0
            sib = el.find_next_sibling()
            while sib and count < 20:
                txt = sib.get_text(separator=' ', strip=True)
                if txt:
                    if sib.name and re.match(r'h[1-6]', sib.name, flags=re.I):
                        break
                    add_candidate_to_list(txt, offers, seen)
                sib = sib.find_next_sibling()
                count += 1

        visible = soup.get_text(separator='\n', strip=True)
        found = re.findall(r'(?i)Bank Offer[:\-\s]*([^\n]{10,200})', visible)
        for f in found:
            add_candidate_to_list(f, offers, seen)

        return offers
    except Exception:
        return None

    # Note: previous return above exits on success; keep fallback/second-pass below


def fetch_product_info_from_page(first_item: Dict[str, Any], oxylabs_result: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Fetch the product page (from URL or ASIN) and extract common product fields."""
    identifier = first_item.get('url') or first_item.get('asin')
    if not identifier:
        return None
    product_url = identifier if isinstance(identifier, str) and identifier.startswith('http') else f"https://www.amazon.in/dp/{identifier}"

    soup = fetch_product_page(product_url)
    if not soup:
        return None

    title = safe_select_text(soup, '#productTitle') or safe_select_text(soup, 'h1')
    # price heuristics
    price = None
    for sel in ('#priceblock_ourprice', '#priceblock_dealprice', 'span.a-price span.a-offscreen', 'span.a-price-whole'):
        v = safe_select_text(soup, sel)
        if v:
            price = v
            break
    # image
    image = None
    img = soup.select_one('#imgTagWrapperId img')
    if img:
        image = img.get('data-old-hires') or img.get('src')
    if not image:
        og = soup.select_one('meta[property="og:image"]')
        if og:
            image = og.get('content')
    # rating and reviews
    rating = None
    rnode = soup.select_one('span.a-icon-alt')
    if rnode:
        rating = rnode.get_text().split(' out of ')[0].strip()
    reviews = safe_select_text(soup, '#acrCustomerReviewText')
    bullets = [b.get_text().strip() for b in soup.select('#feature-bullets ul li') if b.get_text().strip()]
    description = extract_description_from_soup(soup)
    bank_offers = extract_bank_offers_from_soup(soup)
  
    return {
        'title': title,
        'asin': first_item.get('asin'),
        'url': product_url,
        'price': price,
        'image': image,
        'rating': rating,
        'reviews_count': reviews,
        'bullets': bullets,
        'raw_first_item': first_item.get('raw'),
        'bank_offers': bank_offers,
    }


# --- Helpers: Oxylabs parsed descriptions fallback ---
def extract_description_from_ox(result_json: Dict[str, Any]) -> Optional[str]:
    try:
        results = result_json.get('results', [])
        if not results:
            return None
        content = results[0].get('content', {})
        product_result = content.get('product_result') or content.get('results', {}).get('product_result')
        if product_result:
            desc = product_result.get('description') or product_result.get('features')
            if desc:
                if isinstance(desc, list):
                    return '\n'.join([str(x) for x in desc])
                return str(desc)
        organic = content.get('results', {}).get('organic', [])
        if organic:
            raw = organic[0]
            for k in ('excerpt', 'snippet', 'description', 'summary'):
                v = raw.get(k)
                if v:
                    if isinstance(v, list):
                        return '\n'.join([str(x) for x in v])
                    return str(v)
    except Exception:
        pass
    return None


# --- Main flow ---

def single_search_product(query: str = 'vivo x fold 5') -> None:
    # 1) Call Oxylabs search and save raw response
    try:
        result_json = call_oxylabs_search(query)
        # Do not save raw Oxylabs JSON to disk per user's request; keep in memory only
    except Exception as exc:
        print('Oxylabs request failed:', exc)
        # Attempt to continue if a cached raw file exists on disk
      
    # 2) Extract first organic item
    first_item = extract_first_organic(result_json)
    if not first_item:
        print('No first organic item found')
        return
    pprint(first_item)
    # Do not save the raw first_organic JSON file — we only save final product info when complete

    # 3) Try page-based extraction (preferred)
    product_info = fetch_product_info_from_page(first_item, oxylabs_result=result_json)

    return product_info



def get_multi_search_products(query: str, limit: int = 5) -> list:
    """Return up to `limit` product info dicts for the given query.

    Uses Oxylabs parsed results to find the top organic items, then attempts
    to fetch product pages for richer metadata. Falls back to Oxylabs parsed
    snippets when a product page cannot be fetched.
    """
    try:
        result_json = call_oxylabs_search(query)
    except Exception:
        print('Oxylabs request failed')
        return []

    items = extract_top_organic_items(result_json, limit=limit)
    output = []
    for it in items:
        info = fetch_product_info_from_page(it, oxylabs_result=result_json)
        if not info:
            # Try to build minimal info from raw
            info = {'asin': it.get('asin'), 'url': it.get('url')}
            desc = extract_description_from_raw(it.get('raw') or {}) or extract_description_from_ox(result_json)
            if desc:
                info['description'] = desc
        output.append(info or {'asin': it.get('asin'), 'url': it.get('url')})
    return output



def get_amazon_result(tool_result):
    fn = tool_result.get('action', '').strip()
    query = tool_result.get('query', '').strip()
    max_results = tool_result.get('max_results', 5)
    if fn == 'multi_product_search':
        result = get_multi_search_products(query, limit=max_results)
    elif fn == 'single_product_search':
        result = single_search_product(query)
    return result


if __name__ == '__main__':
    # Default single-product flow
   tool_request = {
       "action": "single_product_search",  # or "single_product_search"
       "query": "moto g 96"
   }
   tool_result = get_amazon_result(tool_request)
   with open('amazon_vivo_x_fold_5_product_info.json', 'w', encoding='utf-8') as f:
       json.dump(tool_result, f, ensure_ascii=False, indent=2)
   print(tool_result)