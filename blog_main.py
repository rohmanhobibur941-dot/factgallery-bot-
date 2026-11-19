import os, sys, json, random, glob, time, html, datetime, requests
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 1500  # Pinterest style 2:3 image
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
_extra = os.getenv("GEMINI_MODEL") or ""
MODELS = [m for m in [_extra, "gemini-3.1-flash-lite", "gemini-3.5-flash",
                      "gemini-3.8-flash", "gemini-2.5-flash-lite"] if m]
REPO = os.getenv("GITHUB_REPOSITORY", "user/repo")
BRANCH = os.getenv("GITHUB_REF_NAME", "main")
CATEGORIES = [
    "Human Body Facts", "Brain Facts", "Science Facts", "Space Facts", "Technology",
    "Animal Facts", "History Facts", "Nature", "Psychology", "Amazing Discoveries",
]


# ---------- used facts ----------
def read_used():
    try:
        with open("used.txt", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()][-120:]
    except FileNotFoundError:
        return []


def add_used(topic):
    with open("used.txt", "a", encoding="utf-8") as f:
        f.write(topic.replace("\n", " ").strip() + "\n")


# ---------- 1. Post from Gemini ----------
def gemini_post(category, used):
    prompt = (
        "FactGallery naam ki educational facts website ke liye ek blog post likho.\n"
        "Category: " + category + ".\n"
        "Language: Roman Hinglish (Hindi bolchaal, English akshar me).\n"
        "Rules:\n"
        "- Sirf pakke, jaane-maane, verify ho sakne wale facts. Exact number ya saal ka "
        "pakka pata na ho to 'lagbhag' likho. Kuch bhi jhoot ya andaza mat likho.\n"
        "- title: Hinglish, 70 akshar se kam, curiosity wala, main keyword shuru me.\n"
        "- card_text: image ke upar likhne wali 8-14 shabd ki hairaan karne wali fact line.\n"
        "- image_prompt: English me ek line, is fact ki realistic photo ka description "
        "(vertical, koi text ya logo nahi).\n"
        "- intro: 2-3 line ki shuruaat.\n"
        "- facts: 5 chhote facts (har ek 1-2 line) isi topic par.\n"
        "- did_you_know: ek chhoti aur dilchasp line.\n"
        "- tags: 3 chhote English tags.\n"
        "- topic: is fact ka 4-8 shabd ka chhota naam (repeat pehchanne ke liye).\n"
    )
    if used:
        prompt += "Ye topics pehle ban chuke hain, inhe repeat MAT karo:\n- " + "\n- ".join(used) + "\n"
    prompt += ('Sirf valid JSON: {"title":"","card_text":"","image_prompt":"","intro":"",'
               '"facts":["","","","",""],"did_you_know":"","tags":["","",""],"topic":""}')
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
    }
    for model in MODELS:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
               % model)
        print("Trying model:", model)
        for attempt in range(2):
            try:
                r = requests.post(url, headers={"x-goog-api-key": GEMINI_KEY},
                                  json=body, timeout=300)
            except requests.RequestException as e:
                print("Gemini request error:", e)
                time.sleep(10)
                continue
            if r.status_code == 200:
                try:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(txt)
                    if data.get("title") and data.get("facts"):
                        return data
                except Exception as e:
                    print("Gemini parse error:", e)
                time.sleep(5)
                continue
            print("Gemini error", r.status_code, r.text[:200])
            if r.status_code in (404, 429, 403):
                break
            time.sleep(10)
    raise RuntimeError("Gemini post failed")


# ---------- 2. Image ----------
def ai_image(prompt, path):
    full = prompt + ", realistic photo, cinematic lighting, vertical, no text, no watermark"
    for attempt in range(4):
        try:
            r = requests.get(
                "https://image.pollinations.ai/prompt/" + quote(full),
                params={"width": W, "height": H, "model": "flux", "nologo": "true",
                        "seed": random.randint(1, 10**6)},
                timeout=120,
            )
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(path, "wb") as fh:
                    fh.write(r.content)
                Image.open(path).verify()
                return True
            print("Pollinations status:", r.status_code)
        except Exception as e:
            print("Pollinations error:", e)
        time.sleep(20 * (attempt + 1))
    return False


def load_font(size):
    cands = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"]
    cands += glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)
    for p in cands:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise RuntimeError("Font not found")


def gradient_base():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(230 - 205 * t), int(0 + 25 * t), int(35 - 10 * t)))
    return img


def make_card(base_path, text, category, out):
    """Image par bada text, category badge aur FactGallery naam lagata hai."""
    if base_path and os.path.exists(base_path):
        bg = Image.open(base_path).convert("RGB")
        scale = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1))
        l, t = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((l, t, l + W, t + H))
    else:
        bg = gradient_base()
    img = bg.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H):
        a = int(230 * max(0.0, (y - H * 0.40) / (H * 0.60)))
        sd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)

    words = text.split()
    box_w = W - 120
    for size in range(84, 38, -4):
        font = load_font(size)
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if d.textlength(test, font=font) <= box_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        lh = int(size * 1.25)
        if len(lines) <= 6 and all(d.textlength(x, font=font) <= box_w for x in lines):
            break
    y = H - 170 - lh * len(lines)
    for k, line in enumerate(lines):
        d.text((60, y + k * lh), line, font=font, fill="white",
               stroke_width=4, stroke_fill="black")

    bf = load_font(38)
    tw = d.textlength(category.upper(), font=bf)
    d.rectangle([50, 50, 50 + tw + 50, 130], fill=(230, 0, 35))
    d.text((75, 64), category.upper(), font=bf, fill="white")
    ff = load_font(36)
    brand = "FactGallery"
    d.text(((W - d.textlength(brand, font=ff)) / 2, H - 90), brand, font=ff,
           fill=(255, 255, 255, 230))
    img.convert("RGB").save(out, quality=85, optimize=True)


# ---------- 3. HTML ----------
def build_html(d, img_url):
    e = html.escape
    parts = [
        '<div class="separator" style="clear: both; text-align: center;">'
        '<img alt="%s" border="0" src="%s" width="1000" height="1500" '
        'style="max-width: 100%%; height: auto;" /></div>' % (e(d["title"]), e(img_url)),
        "<p>%s</p>" % e(d.get("intro", "")),
        "<h2>Key Facts</h2>",
        "<ul>" + "".join("<li>%s</li>" % e(str(f)) for f in d["facts"]) + "</ul>",
    ]
    if d.get("did_you_know"):
        parts += ["<h2>Kya aap jaante the?</h2>", "<p>%s</p>" % e(d["did_you_know"])]
    parts.append("<p>Aisi aur dilchasp facts ke liye FactGallery ko follow karte rahein.</p>")
    return "\n".join(parts)


# ---------- commands ----------
def generate():
    os.makedirs("images", exist_ok=True)
    os.makedirs("work", exist_ok=True)
    category = os.getenv("CATEGORY") or random.choice(CATEGORIES)
    print("Category:", category)
    data = gemini_post(category, read_used())
    print("Title:", data["title"])

    name = "%s-%04d.jpg" % (datetime.date.today().isoformat(), random.randint(0, 9999))
    base = "work/base.jpg"
    ok = ai_image(data.get("image_prompt") or data.get("topic") or category, base)
    if not ok:
        print("AI image nahi bani, simple gradient card use hoga")
        base = None
    out = os.path.join("images", name)
    make_card(base, data.get("card_text") or data["title"], category, out)
    make_card(base, data.get("card_text") or data["title"], category, "work/preview.jpg")

    img_url = "https://cdn.jsdelivr.net/gh/%s@%s/images/%s" % (REPO, BRANCH, name)
    post = {
        "title": data["title"],
        "content": build_html(data, img_url),
        "labels": [category] + [str(t) for t in data.get("tags", [])][:3],
        "topic": data.get("topic") or data["title"],
    }
    with open("work/post.json", "w", encoding="utf-8") as fh:
        json.dump(post, fh, ensure_ascii=False)
    print("Generated:", name)


def publish():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    with open("work/post.json", encoding="utf-8") as fh:
        post = json.load(fh)
    creds = Credentials(
        None,
        refresh_token=os.environ["BLOG_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    creds.refresh(Request())
    svc = build("blogger", "v3", credentials=creds, cache_discovery=False)
    res = svc.posts().insert(
        blogId=os.environ["BLOG_ID"],
        body={"kind": "blogger#post", "title": post["title"],
              "content": post["content"], "labels": post["labels"]},
        isDraft=False,
    ).execute()
    print("Published:", res.get("url"))
    add_used(post["topic"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if cmd == "generate":
        generate()
    elif cmd == "publish":
        publish()
    else:
        print("Use: generate | publish")
