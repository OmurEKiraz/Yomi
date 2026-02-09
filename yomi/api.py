import uvicorn
import os
import json
import shutil
import aiohttp
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from difflib import SequenceMatcher

# Internal Package Imports
from .core import YomiCore
from .extractors.common import AsyncGenericMangaExtractor
from .utils.anilist import AniListProvider

app = FastAPI(
    title="Yomi API Service",
    description="Backend Bridge for Yomi Manga Engine",
    version="0.1.1"
)

# Enable CORS for Flutter/Web integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Core Services
yomi = YomiCore(output_dir="downloads", workers=8)
anilist = AniListProvider()

# Global state to track background downloads
download_registry: Dict[str, dict] = {}

@app.get("/")
async def root():
    """Service Health Check"""
    return {
        "status": "active",
        "engine": "Yomi-Core",
        "database_version": "v1.2",
        "total_supported_sites": len(yomi.sites_config)
    }

@app.get("/search")
async def search_manga(q: str = Query(..., min_length=2)):
    """Search for manga using fuzzy scoring algorithm"""
    query = q.lower().strip()
    matches = []
    
    for key, data in yomi.sites_config.items():
        name = data.get('name', '').lower()
        # Hybrid scoring: Sequence similarity + Substring match
        score = SequenceMatcher(None, query, key).ratio() * 100
        if query in key or query in name: 
            score += 25  # Relevance boost
        
        if score > 40:
            matches.append({
                "slug": key,
                "name": data.get('name', key),
                "confidence": min(int(score), 100),
                "base_domain": data.get('base_domain')
            })
    
    # Sort by highest confidence first
    results = sorted(matches, key=lambda x: x['confidence'], reverse=True)
    return {"query": q, "results": results[:15]}

@app.get("/manga/details")
async def get_details(slug: str):
    """Fetch chapters and external metadata (AniList)"""
    url = await yomi._resolve_target(slug)
    if not url:
        raise HTTPException(status_code=404, detail="Manga slug not found")

    async with aiohttp.ClientSession() as session:
        extractor = AsyncGenericMangaExtractor(session)
        # Fetch chapter list from mirror
        chapters = await extractor.get_chapters(url)
        # Fetch metadata from AniList based on title
        manga_info = await extractor.get_manga_info(url)
        metadata = await anilist.fetch_metadata(manga_info['title'])
        
        return {
            "slug": slug,
            "title": manga_info['title'],
            "source_url": url,
            "metadata": metadata,
            "chapters": chapters
        }

@app.post("/download/start")
async def start_task(slug: str, chapters: Optional[str] = None, background_tasks: BackgroundTasks = None):
    """Trigger a download task in the background"""
    if slug in download_registry and download_registry[slug]['status'] == "processing":
        return {"status": "error", "message": "Task already in progress"}

    download_registry[slug] = {
        "status": "processing",
        "requested_range": chapters or "all",
        "timestamp": datetime.now().isoformat()
    }

    def execute():
        try:
            yomi.download_manga(slug, chapters)
            download_registry[slug]['status'] = "completed"
        except Exception as e:
            download_registry[slug]['status'] = f"failed: {str(e)}"

    background_tasks.add_task(execute)
    return {"status": "queued", "slug": slug}

@app.get("/download/tasks")
async def monitor_tasks():
    """Monitor active and finished background tasks"""
    return download_registry

@app.get("/library")
async def list_library():
    """Scan local storage for downloaded content"""
    if not os.path.exists(yomi.output_dir):
        return {"items": []}
    
    local_content = []
    for folder in os.listdir(yomi.output_dir):
        folder_path = os.path.join(yomi.output_dir, folder)
        if os.path.isdir(folder_path):
            files = os.listdir(folder_path)
            local_content.append({
                "manga_name": folder,
                "chapter_count": len(files),
                "path": os.path.abspath(folder_path)
            })
    return {"library": local_content}

def start_api():
    """Start the Uvicorn ASGI server"""
    uvicorn.run(app, host="0.0.0.0", port=8000)





if __name__ == "__main__":
    run_server()