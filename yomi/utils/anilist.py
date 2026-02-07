import aiohttp
import logging
from difflib import SequenceMatcher

logger = logging.getLogger("YomiCore")

class AniListProvider:
    def __init__(self):
        self.api_url = 'https://graphql.anilist.co'
        self.cache = {}

    def calculate_similarity(self, a, b):
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    async def fetch_metadata(self, manga_name: str):
        if manga_name in self.cache:
            return self.cache[manga_name]

        query = '''
        query ($search: String) {
          Media (search: $search, type: MANGA) {
            title { romaji english }
            staff {
              edges {
                role
                node { name { full } }
              }
            }
            startDate { year }
            genres
            description
          }
        }
        '''
        variables = {'search': manga_name}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json={'query': query, 'variables': variables}, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        media = data['data']['Media']
                        
                        # Fuzzy match kontrolü (Yanlış mangayı çekmeyelim)
                        titles = [media['title']['romaji'], media['title']['english']]
                        best_match = max([self.calculate_similarity(manga_name, t) for t in titles if t])
                        
                        if best_match > 0.7:
                            meta = self._format_meta(media)
                            self.cache[manga_name] = meta
                            return meta
        except Exception as e:
            logger.debug(f"AniList Error: {e}")
        return None

    def _format_meta(self, media):
        writer, artist = "", ""
        for edge in media['staff']['edges']:
            role, name = edge['role'].lower(), edge['node']['name']['full']
            if 'story' in role or 'writer' in role: writer = name
            if 'art' in role or 'illustrator' in role: artist = name
        
        return {
            "writer": writer or artist,
            "artist": artist or writer,
            "year": media['startDate']['year'],
            "genres": ", ".join(media['genres']),
            "summary": media['description'].replace("<br>", "\n").strip() if media['description'] else ""
        }