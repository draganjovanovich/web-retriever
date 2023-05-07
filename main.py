import io
import json
import httpx
import PyPDF2
from fastapi import FastAPI, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

PROJECT_NAME = "web-retriever"
ACCOUNT_NAME = "draganjovanovich"
CHAR_LIMIT = 1280

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def truncate_paragraphs(paragraphs, max_length):
    truncated_paragraphs = []
    current_length = 0

    for paragraph in paragraphs:
        if current_length + len(paragraph) <= max_length:
            truncated_paragraphs.append(paragraph)
            current_length += len(paragraph)
        else:
            remaining_length = max_length - current_length
            truncated_paragraph = paragraph[:remaining_length]
            truncated_paragraphs.append(truncated_paragraph)
            break

    return truncated_paragraphs

@app.get("/get-url-content/", operation_id="getUrlContent", summary="It will return a web page's or pdf's content")
async def get_url_content(url: str = Query(..., description="url to fetch content from")) -> Response:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()  # Raise an exception for HTTP errors

        if url.endswith(".pdf"):
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()

            text = text[0:CHAR_LIMIT]
        else:
            soup = BeautifulSoup(response.text, "html.parser")

            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
            truncated_paragraphs = truncate_paragraphs(paragraphs, CHAR_LIMIT)

            images = []
            for p in soup.find_all("p"):
                parent = p.parent
                images.extend([img["src"]
                               for img in parent.find_all("img") if img.get("src")])
            if len(images) > 3:
                images = images[:3]

            data = {"text": truncated_paragraphs, "images": images}
            # if you want plain text ...
            text = json.dumps(data)
            text = f"""{text}
You MUST include images from "images" list above, if there are any.
When responding to Human, format images with markdown. Example: ![](image_link)
You wont make up your own links for images but will use provided ones in "images" list above!
Remember to include images if there are links below!
Do not repeat same images over and over again!
"""
        return Response(content=text, media_type="text/plain")

    except Exception as e:
        print(e)
        error_message = f"Sorry, the url is not available. {e}\nYou should report this message to the user!"
        return JSONResponse(content={"error": error_message}, status_code=500)

@app.get("/icon.png", include_in_schema=False)
async def api_icon():
    with open("icon.png", "rb") as f:
        icon = f.read()
    return Response(content=icon, media_type="image/png")

@app.get("/ai-plugin.json", include_in_schema=False)
async def api_ai_plugin():
    with open("ai-plugin.json", "r") as f:
        ai_plugin_json = json.load(f)
    return Response(content=json.dumps(ai_plugin_json), media_type="application/json")

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Web Retriever",
        version="0.1",
        routes=app.routes,
    )
    openapi_schema["servers"] = [
        {
            "url": f"https://{PROJECT_NAME}-{ACCOUNT_NAME}.vercel.app",
        },
    ]
    openapi_schema["tags"] = [
        {
            "name": "web-retriever",
            "description": "",
        },
    ]
    openapi_schema.pop("components", None)
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi