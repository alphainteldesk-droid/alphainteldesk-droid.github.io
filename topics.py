# Alpha Intel Desk: picks a topic emoji for a market. Shared by the Telegram scripts.
import re

# The first match wins, so more specific topics come first.
TOPICS = [
    ("🎮", r"dota|cs2|counter-strike|league of legends|valorant|esports?|overwatch|rocket league"),
    ("🎾", r"tennis|atp|wta|wimbledon|us open|french open|australian open|paris masters|tennis open"),
    ("🏈", r"nfl|super bowl|football|touchdown|ncaaf"),
    ("🏀", r"nba|wnba|basketball|ncaab|march madness"),
    ("⚾", r"mlb|baseball|world series"),
    ("🏒", r"nhl|hockey|stanley cup"),
    ("⚽", r"soccer|premier league|champions league|la liga|serie a|bundesliga|mls|fifa|world cup|fc"),
    ("⛳", r"golf|pga|liv golf|ryder cup|augusta"),
    ("🏏", r"cricket|t20|ipl"),
    ("🥊", r"ufc|boxing|mma"),
    ("🏎️", r"f1|formula 1|grand prix|nascar"),
    ("₿", r"bitcoin|btc"),
    ("🪙", r"crypto|ethereum|eth|solana|xrp|dogecoin|algorand|algo"),
    ("⛽", r"gas prices?|gasoline|oil|crude|brent|wti|opec"),
    ("🏦", r"fed|fomc|interest rates?|rate cut|rate hike|inflation|cpi|gdp|jobs report|unemployment|recession|bank of england|ecb"),
    ("📈", r"s&p|nasdaq|dow|stocks?|earnings|tesla|nvidia|apple|ipo"),
    ("🗳️", r"elections?|senate|house control|house seats?|governor|mayor|primary|midterms?|nominee|votes?|ballot"),
    ("🏛️", r"trump|congress|supreme court|president|white house|shutdown|tariffs?"),
    ("🌍", r"war|ukraine|russia|israel|iran|gaza|china|ceasefire|strait|nato"),
    ("🌦️", r"weather|temperature|rain|snow|hurricane|storm|degrees"),
    ("🎬", r"movie|box office|oscars?|emmys?|netflix|film|tv show"),
    ("🎵", r"grammys?|album|song|spotify|billboard|taylor swift"),
    ("🤖", r"ai|openai|chatgpt|gpt|anthropic|gemini"),
    ("🚀", r"spacex|nasa|launch|starship|rocket"),
    ("🐦", r"tweets?|elon|musk"),
]

# Kalshi titles often skip the league name ("New York J vs Kansas City"),
# but the link has it (kalshi.com/markets/kxnflgame), so check the link too.
LINKS = [
    ("🏈", r"nfl|ncaaf|cfb"), ("🏀", r"nba|wnba|ncaab|ncaamb|ncaawb"), ("⚾", r"mlb"),
    ("🏒", r"nhl"), ("⚽", r"epl|laliga|seriea|bundesliga|ucl|mls|soccer|ligue"),
    ("🏏", r"t20|cricket|ipl|odi"), ("🎾", r"atp|wta|tennis"), ("⛳", r"pga|golf"),
    ("🥊", r"ufc|boxing"), ("🏎️", r"f1|nascar"), ("🎮", r"dota|cs2|lol|valorant|esport"),
]

def topic(text, url=""):
    t = text.lower()
    for emoji, words in TOPICS:
        if re.search(r"\b(" + words + r")\b", t):
            return emoji
    slug = url.lower().rsplit("/", 1)[-1]
    for emoji, words in LINKS:
        if re.search(words, slug):
            return emoji
    return "📊"
