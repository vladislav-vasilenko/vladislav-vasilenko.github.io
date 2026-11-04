"""Job market from the vacancy's own location, falling back to the employer's catalog region when it is blank."""
import re

MARKETS = ('ru', 'us', 'south_america', 'uk', 'canada', 'europe', 'china', 'japan', 'au_nz', 'other')
# Order matters: Canadian and UK places first, since they share names and abbreviations with US patterns.
PATTERNS = (
    ('canada', r'canada|toronto|vancouver|montreal|ottawa|ontario|, ?(?:on|bc|qc)\b'),
    ('uk', r'united kingdom|\buk\b|london|england|scotland|edinburgh|manchester'),
    ('south_america', r'brazil|brasil|são paulo|sao paulo|argentina|buenos aires|chile|santiago|colombia|bogot|mexico|peru|uruguay'),
    ('china', r'china|beijing|shanghai|shenzhen|hangzhou|guangzhou|hong kong|китай'),
    ('japan', r'japan|tokyo|япони'),
    ('au_nz', r'australia|sydney|melbourne|new zealand|auckland'),
    ('ru', r'росси|russia|москв|moscow|санкт|петербург|новосибирск|екатеринбург|казан|нижн|краснодар|самар|иннополис'),
    ('europe', r'germany|berlin|munich|france|paris|netherlands|amsterdam|ireland|dublin|spain|madrid|barcelona|poland|warsaw|switzerland|zurich|sweden|stockholm|italy|portugal|lisbon|belgium|austria|czech|prague|denmark|norway|finland|romania|greece|europe|emea|\beu\b'),
    ('us', r'united states|\busa?\b|new york|san francisco|seattle|boston|austin|chicago|los angeles|palo alto|mountain view|sunnyvale|san jose|bellevue|washington|atlanta|denver|, ?(?:ca|ny|wa|tx|ma|il|co|ga|va|pa)\b'),
)
FALLBACK = {'rus': 'ru', 'china': 'china', 'jp': 'japan', 'au_nz': 'au_nz'}


def market_of(row):
    location = (row.get('location') or '').lower()
    for market, pattern in PATTERNS:
        if re.search(pattern, location): return market
    if location.strip(): return 'other'
    return FALLBACK.get(row.get('company_region'), 'other')
