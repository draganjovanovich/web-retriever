import io
import json
import re
import yaml
import httpx
import PyPDF2
from fastapi import FastAPI, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

PROJECT_NAME = "web-retriever"
ACCOUNT_NAME = "draganjovanovich"

# In total, the text + image links + prompts should be <= 2048
CHAR_LIMIT = 1585
IMAGES_CHAR_LIMIT = 300

IMAGES_SUFIX = """, and I will also include images in the format like this: ![](image url)"""

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def extract_image_links(text: str):
    image_pattern = r'https?://\S+\.(?:jpg|jpeg|png|gif|bmp|webp|svg)'
    images = re.findall(image_pattern, text, flags=re.IGNORECASE)
    return images


def detect_content_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    elif (content).upper().startswith(b"<!DOCTYPE HTML") or content.startswith(b"<html"):
        return "text/html"
    elif content.startswith(b"{") or content.startswith(b"["):
        try:
            json.loads(content)
            return "application/json"
        except json.JSONDecodeError:
            pass
    elif content.startswith(b"---") or content.startswith(b"%YAML"):
        try:
            yaml.safe_load(content)
            return "application/x-yaml"
        except yaml.YAMLError:
            pass

    return "text/plain"


def limit_image_count(images, max_chars=300):
    limited_images = []
    current_length = 0

    for url in images:
        # Add the length of "http:" if the URL starts with "//"
        url_length = len("http:") + \
            len(url) if url.startswith("//") else len(url)

        if current_length + url_length > max_chars:
            break

        if url.startswith("//"):
            limited_images.append(f"http:{url}")
        else:
            limited_images.append(url)

        current_length += url_length

    return limited_images


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

        content = response.content
        content_type = detect_content_type(content)
        text = ""
        images = []

        if content_type == "application/pdf":
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()

        if content_type == "text/html":
            soup = BeautifulSoup(response.text, "html.parser")

            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
            # if there are no paragraphs, try to get text from divs
            if not paragraphs:
                paragraphs = [p.get_text(strip=True)
                              for p in soup.find_all("div")]
            # if there are no paragraphs or divs, try to get text from spans
            if not paragraphs:
                paragraphs = [p.get_text(strip=True)
                              for p in soup.find_all("span")]

            text = truncate_paragraphs(paragraphs, CHAR_LIMIT)
            text = " ".join(text)

            for p in soup.find_all("p"):
                parent = p.parent
                images.extend([img["src"]
                               for img in parent.find_all("img") if img.get("src")])

        if content_type == "application/json":
            json_data = json.loads(response.text)
            text = yaml.dump(json_data, sort_keys=False,
                             default_flow_style=False)

            for _, value in json_data.items():
                if isinstance(value, str):
                    images.extend(extract_image_links(value))
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            images.extend(extract_image_links(item))

        if content_type == "text/plain":
            text = response.text
            images = [line for line in text.split('\n') if line.endswith(".jpg") or line.endswith(".png") or line.endswith(
                ".jpeg") or line.endswith(".gif") or line.endswith(".webp") or line.endswith(".svg")]

        images = [f"http:{url}" if url.startswith(
            "//") else url for url in images]
        images = limit_image_count(images, max_chars=IMAGES_CHAR_LIMIT)

        if len(text) > CHAR_LIMIT:
            text = text[:CHAR_LIMIT]

        text_yaml = "text_content: |\n"
        for line in text.split('\n'):
            text_yaml += f"  {line}\n"

        images_yaml = "images:\n" if len(images) > 0 else ""
        for image in images:
            images_yaml += f"- {image}\n"

        yaml_text = f"{text_yaml}\n{images_yaml}"
        text = f"""{yaml_text}
I now know the final answer{IMAGES_SUFIX if len(images) > 0 else "."}
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
