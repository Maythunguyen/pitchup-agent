
# LLM utilities — llm_do() and screenshot compression
import base64
import io
from PIL import Image
from dotenv import load_dotenv

load_dotenv()  # ← must be before OpenAI()

from openai import OpenAI

_openai = OpenAI()

def compress_screenshot(b64_data: str, max_width: int = 1280) -> str:
    """Resize and compress screenshot to reduce token usage."""
    img_bytes = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(img_bytes))
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def llm_do(prompt, output=None, model="gpt-4o", temperature=0.1, system=None, image_b64=None):
    """Call OpenAI like a simple function. Optionally parse response into a Pydantic model."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})

    content = []
    if image_b64:
        if image_b64.startswith("data:image"):
            image_b64 = image_b64.split(",", 1)[1].split("\n")[0].strip()
        image_b64 = compress_screenshot(image_b64)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
        })

    if output:
        content.append({"type": "text", "text": f"{prompt}\n\nReturn ONLY valid JSON. No markdown."})
    else:
        content.append({"type": "text", "text": prompt})

    messages.append({"role": "user", "content": content})

    response = _openai.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages
    )
    raw = response.choices[0].message.content.strip()

    if output is None:
        return raw

    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return output(**__import__("json").loads(raw.strip()))
    except Exception as e:
        raise ValueError(f"Failed to parse response: {e}")