"""
Website Builder — Award-quality, topic-specific websites

Pipeline:
  1. Classify the topic → pick real industry-leading reference sites
  2. Visit 3-4 sites with Playwright, take full screenshots of each
  3. Gemini Vision analyzes ALL screenshots — extracts layout, colour, animations
  4. Gemini fuses concepts from multiple sites into one unique brief
  5. Generate complete HTML/CSS/JS (GSAP, Three.js where appropriate)
  6. Validate, serve locally, verify HTTP 200, open in browser
"""

from __future__ import annotations
import asyncio, base64, io, json, os, random, re, socket, subprocess
import sys, threading, time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


# ── Layout Variants — each is a fundamentally different design approach ────────
# One is picked randomly per build so every site looks genuinely different.
LAYOUT_VARIANTS = [
    {
        "id": "cinematic",
        "name": "Cinematic Full-Bleed",
        "hero": (
            "100vh full-bleed dark hero. A large CSS-drawn abstract shape (circle, arc, or "
            "diagonal slash) fills most of the background. Headline floats center in massive "
            "white/off-white serif — minimum 12vw. A single short line of copy below. "
            "NO button border box — just a text link with an arrow that slides right on hover."
        ),
        "layout": (
            "1. HERO (full-bleed cinematic as above)\n"
            "2. HORIZONTAL SCROLL section — GSAP pinned, cards slide left on scroll\n"
            "3. FULL-WIDTH quote/manifesto — single sentence, huge italic serif, centered\n"
            "4. ALTERNATING rows — image left/text right, then text left/image right (CSS shapes as images)\n"
            "5. CONTACT — just email address in giant monospace font, no form\n"
            "6. FOOTER — single line, tiny text, left/right columns"
        ),
        "special": "GSAP ScrollTrigger horizontal pin, parallax on background shapes, text reveal clip-path",
        "no_generic": "NO standard card grid. NO features checklist. NO pricing table.",
    },
    {
        "id": "editorial",
        "name": "Editorial Magazine",
        "hero": (
            "Split 50/50 layout. LEFT half: background color (from palette), huge vertical "
            "serif headline running top-to-bottom, a thin rule line. RIGHT half: a large CSS "
            "gradient rectangle simulating a photograph, with a small caption text. "
            "Nav is completely minimal — just the brand name left, one CTA right."
        ),
        "layout": (
            "1. HERO (split as above — no full-bleed, just two columns)\n"
            "2. EDITORIAL GRID — 3 col CSS grid, spans different sizes, like a magazine spread\n"
            "3. PULL QUOTE — full width, italic serif, 5vw size, colored background band\n"
            "4. SCROLLING MARQUEE — brand name or slogan repeating left-to-right continuously\n"
            "5. CONTENT COLUMNS — 2 col, image left, text right with index numbers\n"
            "6. FOOTER — newspaper style, 4 columns, thin rules between them"
        ),
        "special": "CSS marquee animation, editorial typography hierarchy, no rounded corners anywhere",
        "no_generic": "NO hero button. NO feature cards with icons. NO glassmorphism.",
    },
    {
        "id": "brutalist",
        "name": "Neo-Brutalist",
        "hero": (
            "Black background OR stark white. Typography is the hero — the brand name in "
            "a massive display font (Bebas Neue or similar) at 20-25vw, uppercase, possibly "
            "overlapping the nav. A blinking cursor character _ after the tagline. "
            "Borders are thick (3-4px), visible, raw."
        ),
        "layout": (
            "1. HERO (brutal typography as above)\n"
            "2. NUMBERED LIST section — items like '01 / 02 / 03' with thick top borders\n"
            "3. ASYMMETRIC — oversized number left (10vw), text right, offset by 30%\n"
            "4. GALLERY — tight grid with thick gaps, images are CSS color blocks + text overlay\n"
            "5. MANIFESTO — bold text, every sentence on its own line, staggered left indent\n"
            "6. FOOTER — plain, monospace font, raw links, thick top border"
        ),
        "special": "Blinking cursor CSS animation, text scramble on hover (JS), thick borders, zero gradients",
        "no_generic": "NO soft shadows. NO rounded corners. NO background gradients. NO glassmorphism.",
    },
    {
        "id": "kinetic",
        "name": "Kinetic Scroll Story",
        "hero": (
            "Almost empty screen — just the headline text, which is SPLIT into individual "
            "words or letters that GSAP assembles from random positions as the page loads. "
            "Background is pure black or deep color. As user scrolls, the hero text "
            "transforms/morphs into the next section's headline."
        ),
        "layout": (
            "1. HERO (kinetic assembly animation)\n"
            "2. STICKY SCROLL — section is pinned for 300vh, content changes as user scrolls:\n"
            "   - Each scroll increment reveals a new fact/product with GSAP\n"
            "3. COUNTER SECTION — animated numbers count up when scrolled into view\n"
            "4. FULL-SCREEN VIDEO-STYLE — CSS gradient animation simulating video background\n"
            "5. TESTIMONIAL — single quote that types itself character by character\n"
            "6. FOOTER — radically minimal, just copyright and two links"
        ),
        "special": "GSAP letter-by-letter reveal, ScrollTrigger pin with 300vh scroll, number counter, typing effect",
        "no_generic": "NO feature grid. NO card layout. Structure is purely scroll-driven storytelling.",
    },
    {
        "id": "luxury_minimal",
        "name": "Luxury Minimal",
        "hero": (
            "Cream/off-white (#faf8f4) background. Extremely refined. The headline is in a "
            "high-end serif at 6-8vw, NOT centered — aligned left with a 10% left margin. "
            "A thin vertical rule line on the left. Nav is invisible until scroll. "
            "One image (CSS shape) positioned absolutely, slightly off-screen right, overlapping the fold."
        ),
        "layout": (
            "1. HERO (refined left-aligned as above)\n"
            "2. PRODUCT ROW — 4 items in a horizontal line, each with tiny image placeholder, "
            "   name in small caps, thin rule below\n"
            "3. FULL-WIDTH IMAGE — dark CSS gradient block taking full width, white text inside\n"
            "4. TEXT-HEAVY section — two columns of body copy, drop cap on first letter\n"
            "5. SINGLE CTA — just one sentence and an underline-link, centered, lots of space\n"
            "6. FOOTER — two lines only, centered, brand name and copyright"
        ),
        "special": "Drop cap CSS, mix-blend-mode multiply on image overlaps, text fade-in on scroll, hairline borders",
        "no_generic": "NO bold accent colors. NO gradients. NO feature icons. Maximum whitespace.",
    },
    {
        "id": "immersive_dark",
        "name": "Immersive Dark Experience",
        "hero": (
            "Pure black. Animated gradient orbs (CSS radial-gradient + keyframe animation) "
            "drifting slowly in background. Large text with a gradient fill "
            "(linear-gradient text clip). Custom animated cursor that changes color as it "
            "moves over different sections. Subtle particle-like dots (JS canvas or CSS)."
        ),
        "layout": (
            "1. HERO (orbs + gradient text as above)\n"
            "2. GLASS CARDS section — backdrop-filter blur cards floating over dark bg, "
            "   each with gradient border (border-image)\n"
            "3. SPOTLIGHT section — mouse position controls a spotlight effect on content\n"
            "4. STATS row — 4 large numbers with labels, animated count-up\n"
            "5. DARK CTA — full-width section, gradient button, text glow on hover\n"
            "6. FOOTER — dark, social icons only (SVG inline), brand mark centered"
        ),
        "special": "CSS orb animation, gradient text clip, JS mouse spotlight, animated gradient border, canvas particles",
        "no_generic": "NOT a standard dark mode site. The darkness is the visual experience itself.",
    },
]


# ── Industry reference sites ───────────────────────────────────────────────────
# For each category, 4 sites are visited so Gemini can fuse their design DNA.
INDUSTRY_REFS = {
    "car": [
        "https://www.ferrari.com/en-EN",
        "https://www.lamborghini.com/en-en",
        "https://www.bentleymotors.com/en",
        "https://www.rolls-roycemotorcars.com/en_GB/home.html",
    ],
    "clothing": [
        "https://www.gucci.com",
        "https://www.zara.com/us",
        "https://us.louisvuitton.com/eng-us/homepage",
        "https://www.bottegaveneta.com/en-us",
    ],
    "watch": [
        "https://www.rolex.com",
        "https://www.audemarspiguet.com/en",
        "https://www.patek.com/en/home",
        "https://www.iwc.com/en",
    ],
    "jewelry": [
        "https://www.tiffany.com",
        "https://www.cartier.com/en-us",
        "https://www.bulgari.com/en-us",
        "https://www.vancleefarpels.com/us/en/home.html",
    ],
    "hotel": [
        "https://www.aman.com",
        "https://www.fourseasons.com",
        "https://www.belmond.com",
        "https://www.rosewoodhotels.com",
    ],
    "food": [
        "https://www.noma.dk",
        "https://restaurant-guy-savoy.com/en",
        "https://www.alain-ducasse.com/en",
        "https://www.eleven-madison-park.com",
    ],
    "tech": [
        "https://linear.app",
        "https://vercel.com",
        "https://stripe.com",
        "https://www.notion.so",
    ],
    "portfolio": [
        "https://www.awwwards.com/websites/portfolio/",
        "https://dribbble.com/shots/popular",
        "https://www.awwwards.com/websites/",
        "https://www.behance.net/galleries/graphic-design",
    ],
    "agency": [
        "https://www.activetheory.net",
        "https://www.hellomonday.com",
        "https://www.resn.co.nz",
        "https://www.awwwards.com/websites/agency/",
    ],
    "default": [
        "https://www.awwwards.com/websites/",
        "https://www.awwwards.com/",
        "https://dribbble.com/shots/popular",
        "https://www.behance.net/galleries",
    ],
}

# Keyword → category mapping
CATEGORY_KEYWORDS = {
    "car":       ["car", "auto", "vehicle", "ferrari", "lamborghini", "porsche", "bmw", "mercedes", "automotive"],
    "clothing":  ["cloth", "fashion", "wear", "apparel", "dress", "shirt", "brand", "gucci", "zara", "outfit", "collection"],
    "watch":     ["watch", "timepiece", "rolex", "clock", "chronograph", "horology"],
    "jewelry":   ["jewel", "ring", "necklace", "diamond", "gold", "bracelet", "tiffany", "cartier"],
    "hotel":     ["hotel", "resort", "stay", "lodge", "villa", "hospitality", "travel", "retreat"],
    "food":      ["food", "restaurant", "dining", "chef", "cuisine", "menu", "cafe", "bakery"],
    "tech":      ["tech", "saas", "app", "software", "startup", "platform", "tool", "dashboard", "ai"],
    "portfolio": ["portfolio", "designer", "photographer", "artist", "creative", "freelance"],
    "agency":    ["agency", "studio", "digital", "creative agency", "web agency"],
}


def _classify_topic(topic: str) -> str:
    t = topic.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in t for k in keywords):
            return cat
    return "default"


# ── Progress Logger ────────────────────────────────────────────────────────────

class BuildLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(f"[{_ts()}] Ali starting website build...\n", encoding="utf-8")

    def add(self, msg: str):
        line = f"[{_ts()}] {msg}\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"[WEB] {msg}")

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except Exception:
            return "(log unavailable)"


def _ts():
    return datetime.now().strftime("%H:%M:%S")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_free_port(start=8500, end=8600):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return 8500


def _serve(directory: str, port: int):
    dir_str = str(directory)

    class FixedDirHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=dir_str, **kwargs)
        def log_message(self, *a):
            pass

    server = HTTPServer(("", port), FixedDirHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _verify_server(url: str, retries: int = 10, delay: float = 0.4) -> bool:
    import urllib.request
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def _open_browser(url: str):
    try:
        subprocess.Popen(["open", url])
    except Exception:
        pass


def _validate_html(html: str) -> list[str]:
    issues = []
    low = html.lower()
    if "<!doctype html" not in low and "<html" not in low:
        issues.append("missing DOCTYPE/html")
    if "</body>" not in low:
        issues.append("missing </body>")
    if len(html) < 3000:
        issues.append(f"too short ({len(html)} chars)")
    return issues


# ── Multi-site Scraper ─────────────────────────────────────────────────────────

async def _screenshot_sites(urls: list[str], log: BuildLog) -> list[dict]:
    """Visit each URL with Playwright, take a full-page screenshot."""
    results = []
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            for url in urls:
                try:
                    log.add(f"  📸 Visiting: {url}")
                    page = await ctx.new_page()
                    await page.goto(url, timeout=18000, wait_until="domcontentloaded")
                    await asyncio.sleep(2.5)

                    # Dismiss cookie banners
                    for sel in ["[id*='cookie'] button", "[class*='cookie'] button",
                                "[id*='accept']", "[class*='accept']", "button:has-text('Accept')",
                                "button:has-text('I agree')"]:
                        try:
                            btn = await page.query_selector(sel)
                            if btn:
                                await btn.click()
                                await asyncio.sleep(0.5)
                                break
                        except Exception:
                            pass

                    shot = await page.screenshot(full_page=False, type="jpeg", quality=80)
                    b64  = base64.b64encode(shot).decode()

                    # Get page title
                    title = await page.title()
                    results.append({"url": url, "title": title, "screenshot_b64": b64})
                    log.add(f"  ✅ Captured: {title[:60]}")
                    await page.close()

                except Exception as e:
                    log.add(f"  ⚠️  Failed to capture {url}: {e}")
                    continue

            await browser.close()
    except Exception as e:
        log.add(f"Browser session error: {e}")

    log.add(f"Screenshots collected: {len(results)}/{len(urls)}")
    return results


# ── Gemini Vision — Design Fusion ──────────────────────────────────────────────

def _fuse_designs(screenshots: list[dict], topic: str, style: str, category: str, api_key: str, log: BuildLog) -> str:
    """
    Send all screenshots to Gemini Vision.
    Ask it to identify what makes each site special, then fuse the best
    elements from all of them into a unique design brief.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        content_parts = []

        intro = (
            f"You are an award-winning creative director. I've screenshotted {len(screenshots)} "
            f"industry-leading {category} websites.\n"
            f"I need to build a website for: **{topic}** (style: {style})\n\n"
            f"STEP 1 — Analyze each screenshot and identify:\n"
            f"- What makes it visually unique (NOT generic)\n"
            f"- Its hero layout approach\n"
            f"- Color palette and typography choices\n"
            f"- Specific animations or interactions\n"
            f"- One standout design decision worth borrowing\n\n"
            f"STEP 2 — Fuse the BEST elements from all sites:\n"
            f"- Pick the most striking hero layout from site X\n"
            f"- The color palette from site Y\n"
            f"- The product/content presentation from site Z\n"
            f"- The footer/nav from whichever is most elegant\n\n"
            f"STEP 3 — Output a SPECIFIC design brief:\n"
            f"1. COLOR PALETTE (5-6 exact hex codes + usage)\n"
            f"2. TYPOGRAPHY (Google Font names, exact sizes, weights)\n"
            f"3. HERO (exact layout — full-bleed image? split? kinetic text? 3D?)\n"
            f"4. ANIMATION LIST (8-10 specific GSAP/CSS animations)\n"
            f"5. LAYOUT STRUCTURE (section order and layout for each)\n"
            f"6. CONTENT SECTIONS (with example copy for {topic})\n"
            f"7. SPECIAL EFFECTS (cursor, parallax, scroll triggers, noise)\n"
            f"8. WHAT MAKES THIS UNIQUE (the one big idea that sets it apart)\n"
        )
        content_parts.append(intro)

        shots_sent = 0
        for i, site in enumerate(screenshots[:4]):
            content_parts.append(f"\n---\n**Site {i+1}: {site['title']} ({site['url']})**")
            if site.get("screenshot_b64") and shots_sent < 4:
                try:
                    img_bytes = base64.b64decode(site["screenshot_b64"])
                    content_parts.append({"mime_type": "image/jpeg", "data": img_bytes})
                    shots_sent += 1
                except Exception:
                    pass

        log.add(f"Sending {shots_sent} screenshots to Gemini Vision for design fusion...")
        response = model.generate_content(content_parts, request_options={"timeout": 90})
        brief = response.text.strip()
        log.add(f"Design fusion brief: {len(brief)} chars")
        return brief

    except Exception as e:
        log.add(f"Vision fusion error: {e} — using text-based brief")
        return _text_brief(topic, style, category)


def _text_brief(topic: str, style: str, category: str) -> str:
    """Fallback brief when vision isn't available — still category-specific."""
    briefs = {
        "car": (
            "Dark carbon-fibre aesthetic. Colours: #08090b, #e8e6e3, #c0392b, #f39c12.\n"
            "Font: Bebas Neue (headings), Inter (body). Hero: full-bleed car reveal with horizontal scroll.\n"
            "Animations: speed lines, engine rev sound on hover, particle dust trails.\n"
            "Products: 3D tilt cards showing car specs. Big idea: the site ACCELERATES as you scroll."
        ),
        "clothing": (
            "Editorial fashion. Colours: #fafaf8, #1a1a1a, #c9a84c, #e8d5b7.\n"
            "Font: Cormorant Garamond (headings), DM Sans (body). Hero: full-screen lookbook with slow pan.\n"
            "Animations: fabric sway effect, model reveal, collection slideshow.\n"
            "Products: editorial grid, hover zooms to detail. Big idea: feels like a print magazine."
        ),
        "watch": (
            "Swiss precision. Colours: #0d0d0d, #f0ede8, #b8922a, #e8e0d0.\n"
            "Font: Playfair Display (headings), Inter (body). Hero: close-up watch face with ticking second hand.\n"
            "Animations: watch hands tick, dial zoom, sapphire crystal reflection.\n"
            "Products: hero spotlight with 360 rotation. Big idea: the watch ticks as you scroll."
        ),
        "tech": (
            "Minimal SaaS. Colours: #000000, #ffffff, #6366f1, #a855f7.\n"
            "Font: Inter (all), tight tracking. Hero: animated code/dashboard preview.\n"
            "Animations: gradient shimmer, feature highlights, smooth section transitions.\n"
            "Products: feature cards with hover glow. Big idea: feels instant and frictionless."
        ),
        "hotel": (
            "Warm luxury. Colours: #f5f0e8, #2c2416, #b5956a, #8b7355.\n"
            "Font: Canela (headings), Graphik (body). Hero: parallax landscape video.\n"
            "Animations: slow reveal, room tour on scroll, seasonal transitions.\n"
            "Products: room cards with full-bleed imagery. Big idea: the site is a destination itself."
        ),
        "food": (
            "Gastronomic. Colours: #1a1209, #f4ede4, #d4a853, #8b4513.\n"
            "Font: Freight Display (headings), Futura (body). Hero: dish close-up with steam effect.\n"
            "Animations: plating sequence, ingredient reveal, menu unfold.\n"
            "Products: tasting menu cards with course descriptions. Big idea: synesthetic — you can almost smell it."
        ),
    }
    return briefs.get(category, (
        f"Award-winning {style}. Research {topic} industry leaders and borrow their best design decisions.\n"
        "Use bold typography, purposeful whitespace, smooth GSAP animations, and a custom cursor."
    ))


# ── HTML Generator ─────────────────────────────────────────────────────────────

def _generate_html(topic: str, style: str, pages: list, brief: str,
                   category: str, ref_sites: list[dict], api_key: str,
                   log: BuildLog, variant: dict) -> dict[str, str]:
    """Ask Gemini to generate complete HTML using a specific layout variant."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        site_names = [s["title"][:40] for s in ref_sites[:4]] if ref_sites else ["industry leaders"]

        prompt = f"""You are a world-class creative director and front-end developer.
Build a website for Awwwards.com — it MUST win Site of the Day.

TOPIC: {topic}
CATEGORY: {category}
STYLE: {style}
INSPIRED BY: {', '.join(site_names)}

━━━ CHOSEN LAYOUT: {variant["name"].upper()} ━━━
You MUST build the {variant["name"]} layout. This is non-negotiable.

HERO DESIGN (build exactly this):
{variant["hero"]}

SECTION STRUCTURE (follow this order exactly):
{variant["layout"]}

SPECIAL TECHNIQUES (implement ALL of these):
{variant["special"]}

WHAT TO AVOID:
{variant["no_generic"]}

━━━ DESIGN BRIEF FROM REAL {category.upper()} WEBSITES ━━━
{brief}

━━━ TECHNICAL REQUIREMENTS ━━━
CDN scripts allowed:
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/ScrollTrigger.min.js"></script>
Google Fonts via @import inside <style>.
All other CSS inline. All JS inline at bottom. No frameworks.

CUSTOM CURSOR: always include — a small dot + larger ring that lags behind.
LOADING SCREEN: brief overlay that fades out after 800ms.
SEO: <title>, <meta description>, <meta property="og:title">, <link rel="canonical">.

CONTENT: Write real, specific copy for {topic}. No "Lorem ipsum". No placeholder text.
CATEGORY-SPECIFIC CONTENT for {category}:
  - car: model names, 0-100 times, horsepower, price
  - clothing: garment names, materials, sizes, seasons
  - watch: movement type, power reserve, case diameter, collection name
  - hotel: room names, amenities, location details, rates
  - food: dish names, ingredients, chef name, tasting menu
  - tech: feature names, metrics, integration names, pricing tiers
  - default: invent specific, believable details for {topic}

PAGES: {', '.join(pages)}

OUTPUT: One JSON object per page, nothing else before or after:
{{"filename": "index.html", "content": "<COMPLETE HTML — NEVER TRUNCATE>"}}

The HTML must be 500+ lines. Complete working code only.
"""

        log.add("Calling Gemini to generate unique award-quality HTML...")
        log.add("(30-90 seconds for a complete, non-generic build)")

        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": 65536},
            request_options={"timeout": 200},
        )
        raw = response.text.strip()
        log.add(f"Gemini returned {len(raw):,} characters")

        # Parse JSON blocks
        files = {}
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(raw):
            try:
                brace = raw.index('{', idx)
                obj, end = decoder.raw_decode(raw, brace)
                if isinstance(obj, dict) and "filename" in obj and "content" in obj:
                    files[obj["filename"]] = obj["content"]
                    log.add(f"Parsed: {obj['filename']} ({len(obj['content']):,} chars)")
                idx = end
            except (ValueError, KeyError):
                nxt = raw.find('{', idx + 1)
                idx = nxt if nxt > idx else len(raw)

        # Fallback: raw response might be HTML directly
        if not files:
            if raw.strip().lower().startswith("<!doctype") or "<html" in raw[:200].lower():
                files["index.html"] = raw
                log.add("Using raw HTML output as index.html")
            else:
                m = re.search(r'(<!DOCTYPE html.*?</html>)', raw, re.DOTALL | re.IGNORECASE)
                if m:
                    files["index.html"] = m.group(1)
                    log.add("Extracted HTML block as index.html")

        return files

    except Exception as e:
        log.add(f"HTML generation error: {e}")
        return {}


# ── Category-aware Fallback Template ──────────────────────────────────────────

_CATEGORY_THEMES = {
    "car": {
        "bg": "#06080a", "bg2": "#0e1015", "fg": "#e8e6e3",
        "acc": "#c0392b", "acc2": "#f39c12", "font_head": "Bebas+Neue",
        "font_body": "Inter", "font_head_css": "'Bebas Neue', sans-serif",
        "eyebrow": "Performance Redefined",
        "hero_h1_line1": "Born for the", "hero_h1_line2": "Road",
        "hero_sub": "Where engineering meets obsession. Every curve calculated. Every second counted.",
        "cta": "Explore Models",
        "section1": "The Collection", "section1_sub": "Choose Your Legacy",
        "section2": "Performance", "section2_sub": "Engineering Excellence",
    },
    "clothing": {
        "bg": "#fafaf8", "bg2": "#f4f0eb", "fg": "#1a1a1a",
        "acc": "#1a1a1a", "acc2": "#c9a84c", "font_head": "Cormorant+Garamond:wght@300;400;700",
        "font_body": "DM+Sans", "font_head_css": "'Cormorant Garamond', serif",
        "eyebrow": "New Season Collection",
        "hero_h1_line1": "Wear What", "hero_h1_line2": "You Feel",
        "hero_sub": "Curated pieces for the discerning few. Crafted with intention, worn with confidence.",
        "cta": "Shop Collection",
        "section1": "The Edit", "section1_sub": "This Season's Essentials",
        "section2": "Our Philosophy", "section2_sub": "Conscious Craft",
    },
    "watch": {
        "bg": "#0a0a0a", "bg2": "#111111", "fg": "#f0ede8",
        "acc": "#b8922a", "acc2": "#e8e0d0", "font_head": "Playfair+Display:wght@400;700;900",
        "font_body": "Inter", "font_head_css": "'Playfair Display', serif",
        "eyebrow": "Swiss Precision Since 1875",
        "hero_h1_line1": "Time is the", "hero_h1_line2": "Ultimate Luxury",
        "hero_sub": "Every piece measures more than seconds — it measures a life well lived.",
        "cta": "Explore Timepieces",
        "section1": "The Collection", "section1_sub": "Masterpieces of Horology",
        "section2": "The Craft", "section2_sub": "400 Hours of Artisanship",
    },
    "hotel": {
        "bg": "#f5f0e8", "bg2": "#ede8dc", "fg": "#2c2416",
        "acc": "#b5956a", "acc2": "#8b7355", "font_head": "Libre+Baskerville:wght@400;700",
        "font_body": "Lato", "font_head_css": "'Libre Baskerville', serif",
        "eyebrow": "An Escape Beyond Compare",
        "hero_h1_line1": "Where Silence", "hero_h1_line2": "Speaks",
        "hero_sub": "A retreat for those who seek not just comfort, but transformation.",
        "cta": "Reserve Your Stay",
        "section1": "Our Rooms", "section1_sub": "Intimate Spaces",
        "section2": "The Experience", "section2_sub": "A Journey for the Senses",
    },
    "tech": {
        "bg": "#000000", "bg2": "#0a0a0f", "fg": "#ffffff",
        "acc": "#6366f1", "acc2": "#a855f7", "font_head": "Inter:wght@300;400;700;900",
        "font_body": "Inter", "font_head_css": "'Inter', sans-serif",
        "eyebrow": "Next Generation Platform",
        "hero_h1_line1": "Build Faster.", "hero_h1_line2": "Ship Smarter.",
        "hero_sub": "The platform that collapses the distance between idea and reality.",
        "cta": "Start Free",
        "section1": "Features", "section1_sub": "Everything You Need",
        "section2": "Why Us", "section2_sub": "Built Different",
    },
    "food": {
        "bg": "#1a1209", "bg2": "#231810", "fg": "#f4ede4",
        "acc": "#d4a853", "acc2": "#8b4513", "font_head": "Playfair+Display:ital,wght@0,400;1,400;0,700",
        "font_body": "Lato", "font_head_css": "'Playfair Display', serif",
        "eyebrow": "A Culinary Journey",
        "hero_h1_line1": "Taste the", "hero_h1_line2": "Season",
        "hero_sub": "Every dish tells a story. Every ingredient chosen with reverence.",
        "cta": "Reserve a Table",
        "section1": "The Menu", "section1_sub": "Seasonal Tasting",
        "section2": "The Chef", "section2_sub": "Philosophy",
    },
}


def _build_fallback(topic: str, style: str, category: str) -> str:
    t = _CATEGORY_THEMES.get(category, {
        "bg": "#06060a", "bg2": "#0e0e16", "fg": "#f0eef8",
        "acc": "#bf5fff", "acc2": "#ff2d9b", "font_head": "Playfair+Display:wght@400;700;900",
        "font_body": "Inter", "font_head_css": "'Playfair Display', serif",
        "eyebrow": "Premium Experience",
        "hero_h1_line1": "Welcome to", "hero_h1_line2": topic.title(),
        "hero_sub": f"A premium {style} experience crafted with precision.",
        "cta": "Explore",
        "section1": "Featured", "section1_sub": "Curated Selection",
        "section2": "About", "section2_sub": "Our Story",
    })

    yr = time.strftime("%Y")
    brand = topic.split()[0].upper()

    # Card content by category
    cards_html = ""
    card_data = {
        "car":      [("Veloce S", "0-100 in 2.8s · 720hp", "$285,000"),
                     ("Corsa GT", "Twin-turbo · 580hp", "$195,000"),
                     ("Strada R", "AWD · 460hp", "$145,000"),
                     ("Pista X", "Track edition · 850hp", "$420,000")],
        "clothing": [("Silk Blazer", "100% Mulberry Silk", "$890"),
                     ("Tailored Trouser", "Japanese Wool", "$560"),
                     ("Linen Shirt", "Organic Belgian Linen", "$320"),
                     ("Cashmere Coat", "Grade A Mongolian", "$1,450")],
        "watch":    [("Calibre I", "Manual Wind · 72hr reserve", "$12,800"),
                     ("Perpetual II", "Automatic · Moon phase", "$24,500"),
                     ("Tourbillon III", "Flying tourbillon", "$87,000"),
                     ("Sport IV", "Diver 300m · Sapphire", "$9,200")],
        "hotel":    [("Garden Suite", "80m² · Private terrace", "From $1,200/night"),
                     ("Pool Villa", "160m² · Infinity pool", "From $3,800/night"),
                     ("Penthouse", "360m² · Butler service", "From $8,500/night"),
                     ("Studio Retreat", "45m² · Forest view", "From $620/night")],
        "food":     [("Amuse-bouche", "Seasonal garden harvest", ""),
                     ("First Course", "Hand-dived scallop, dashi", ""),
                     ("Main", "Aged duck, black truffle", ""),
                     ("Dessert", "Miso caramel, yuzu", "")],
        "tech":     [("Starter", "Up to 5 users · 10GB", "Free"),
                     ("Pro", "Unlimited users · 100GB", "$49/mo"),
                     ("Enterprise", "Custom · SLA", "Contact us"),
                     ("API", "Full access · 1M req/mo", "$99/mo")],
    }.get(category, [
        (f"{topic.split()[0].title()} One", "Signature edition", "$—"),
        (f"{topic.split()[0].title()} Pro", "Advanced series", "$—"),
        (f"{topic.split()[0].title()} Elite", "Limited edition", "$—"),
        (f"{topic.split()[0].title()} Noir", "Black label", "$—"),
    ])

    for name, detail, price in card_data:
        price_html = f'<div class="card-price">{price}</div>' if price else ""
        cards_html += f"""
      <div class="card reveal">
        <div class="card-visual"></div>
        <div class="card-info">
          <div class="card-name">{name}</div>
          <div class="card-detail">{detail}</div>
          {price_html}
        </div>
      </div>"""

    text_color = "var(--fg)" if t["bg"] not in ("#fafaf8", "#f5f0e8", "#f4ede4") else "var(--bg)"
    dark_mode  = t["bg"] not in ("#fafaf8", "#f5f0e8", "#f4ede4")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{topic.title()} — Premium</title>
<meta name="description" content="Premium {category} experience: {topic}.">
<meta property="og:title" content="{topic.title()}">
<meta property="og:description" content="{t['eyebrow']} — {topic.title()}">
<link rel="canonical" href="https://example.com">
<style>
@import url('https://fonts.googleapis.com/css2?family={t["font_head"]}&family={t["font_body"]}:wght@300;400;500;600&display=swap');
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:{t["bg"]};--bg2:{t["bg2"]};--fg:{t["fg"]};
  --acc:{t["acc"]};--acc2:{t["acc2"]};
  --dim:color-mix(in srgb,var(--fg) 55%,transparent);
  --card:color-mix(in srgb,var(--fg) 4%,transparent);
  --border:color-mix(in srgb,var(--acc) 20%,transparent);
  --font-head:{t["font_head_css"]};
  --font-body:'{t["font_body"]}',sans-serif;
}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--font-body);background:var(--bg);color:var(--fg);overflow-x:hidden;cursor:none}}

/* Cursor */
#cur{{position:fixed;width:10px;height:10px;background:var(--acc);border-radius:50%;pointer-events:none;z-index:9999;transform:translate(-50%,-50%);transition:width .2s,height .2s,background .2s}}
#cur-r{{position:fixed;width:36px;height:36px;border:1px solid var(--acc);border-radius:50%;pointer-events:none;z-index:9998;transform:translate(-50%,-50%);opacity:.5;transition:width .25s,height .25s,opacity .3s}}

/* Loader */
#loader{{position:fixed;inset:0;background:var(--bg);z-index:10000;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:1rem;transition:opacity .8s,visibility .8s}}
#loader.gone{{opacity:0;visibility:hidden}}
.l-bar{{width:200px;height:1px;background:var(--border);position:relative;overflow:hidden}}
.l-bar::after{{content:'';position:absolute;inset:0;background:var(--acc);transform:translateX(-100%);animation:load .9s .2s ease forwards}}
@keyframes load{{to{{transform:translateX(0)}}}}
.l-txt{{font-family:var(--font-head);font-size:.8rem;letter-spacing:.4em;text-transform:uppercase;color:var(--acc);opacity:.7}}

/* Nav */
nav{{position:fixed;top:0;left:0;right:0;z-index:100;padding:1.5rem 5vw;display:flex;align-items:center;justify-content:space-between;transition:all .4s}}
nav.solid{{backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);background:color-mix(in srgb,var(--bg) 80%,transparent);border-bottom:1px solid var(--border);padding:1rem 5vw}}
.nav-logo{{font-family:var(--font-head);font-size:1.4rem;color:var(--acc);text-decoration:none;letter-spacing:.05em}}
.nav-links{{display:flex;gap:2.5rem;list-style:none}}
.nav-links a{{color:var(--dim);text-decoration:none;font-size:.8rem;letter-spacing:.15em;text-transform:uppercase;transition:color .25s}}
.nav-links a:hover{{color:var(--fg)}}

/* Hero */
.hero{{min-height:100vh;display:grid;place-items:center;position:relative;overflow:hidden;padding:10rem 5vw 5rem}}
.hero-bg{{position:absolute;inset:0;background:radial-gradient(ellipse 70% 50% at 50% 40%,color-mix(in srgb,var(--acc) 12%,transparent),transparent 70%),radial-gradient(ellipse 50% 60% at 80% 80%,color-mix(in srgb,var(--acc2) 8%,transparent),transparent 60%)}}
.hero-noise{{position:absolute;inset:0;opacity:.025;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 300 300' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");background-size:250px}}
.hero-inner{{text-align:center;position:relative;z-index:1;max-width:1000px}}
.eyebrow{{display:block;font-size:.7rem;letter-spacing:.5em;text-transform:uppercase;color:var(--acc);margin-bottom:2rem;opacity:0;animation:up .8s .2s both}}
h1.display{{font-family:var(--font-head);font-size:clamp(3.5rem,10vw,9rem);line-height:.92;font-weight:900;letter-spacing:-.025em;margin-bottom:2rem;opacity:0;animation:up .9s .4s both}}
h1.display em{{font-style:italic;color:var(--acc)}}
.hero-p{{font-size:clamp(.95rem,1.8vw,1.15rem);color:var(--dim);max-width:540px;margin:0 auto 3rem;line-height:1.75;opacity:0;animation:up .9s .6s both}}
.btn{{display:inline-flex;align-items:center;gap:.6rem;padding:.9rem 2.5rem;border:1px solid var(--acc);color:var(--acc);font-size:.8rem;letter-spacing:.2em;text-transform:uppercase;text-decoration:none;transition:all .3s;opacity:0;animation:up .9s .8s both}}
.btn:hover{{background:var(--acc);color:var(--bg)}}
@keyframes up{{from{{opacity:0;transform:translateY(35px)}}to{{opacity:1;transform:none}}}}

/* Sections */
.section{{padding:clamp(5rem,10vw,9rem) 5vw}}
.s-label{{display:block;font-size:.65rem;letter-spacing:.45em;text-transform:uppercase;color:var(--acc);margin-bottom:1rem}}
.s-title{{font-family:var(--font-head);font-size:clamp(2rem,5vw,4.5rem);line-height:1;font-weight:700;margin-bottom:1rem}}
.s-sub{{color:var(--dim);font-size:1rem;margin-bottom:3rem}}
.reveal{{opacity:0;transform:translateY(45px);transition:opacity .9s ease,transform .9s ease}}
.reveal.in{{opacity:1;transform:none}}

/* Cards */
.bg2{{background:var(--bg2)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:1px;background:var(--border);margin-top:3rem}}
.card{{background:var(--bg);display:flex;flex-direction:column;transition:background .3s}}
.card:hover{{background:var(--bg2)}}
.card-visual{{aspect-ratio:4/3;background:linear-gradient(135deg,color-mix(in srgb,var(--acc) 8%,var(--bg2)),color-mix(in srgb,var(--acc2) 6%,var(--bg2)));display:grid;place-items:center;overflow:hidden;position:relative}}
.card-visual::after{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 50% 60%,color-mix(in srgb,var(--acc) 15%,transparent),transparent 65%);opacity:0;transition:opacity .5s}}
.card:hover .card-visual::after{{opacity:1}}
.card-shape{{width:70px;height:90px;border:1px solid var(--border);transition:transform .5s}}
.card:hover .card-shape{{transform:scale(1.08) rotate(2deg)}}
.card-info{{padding:1.5rem;border-top:1px solid var(--border)}}
.card-name{{font-family:var(--font-head);font-size:1rem;margin-bottom:.3rem}}
.card-detail{{font-size:.78rem;color:var(--dim);letter-spacing:.05em;margin-bottom:.5rem}}
.card-price{{font-size:.95rem;color:var(--acc)}}

/* Features */
.feat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0;background:var(--border);margin-top:3rem}}
.feat{{background:var(--bg);padding:2.5rem 2rem;border-bottom:1px solid var(--border)}}
.feat:hover{{background:var(--bg2)}}
.feat-n{{font-family:var(--font-head);font-size:2.5rem;color:var(--border);margin-bottom:1rem;line-height:1}}
.feat h3{{font-family:var(--font-head);font-size:1.25rem;margin-bottom:.75rem}}
.feat p{{color:var(--dim);font-size:.875rem;line-height:1.8}}

/* Footer */
footer{{padding:3rem 5vw;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1.5rem}}
.f-brand{{font-family:var(--font-head);font-size:1.1rem;color:var(--acc)}}
.f-links{{display:flex;gap:2rem}}
.f-links a{{color:var(--dim);text-decoration:none;font-size:.75rem;letter-spacing:.15em;text-transform:uppercase;transition:color .2s}}
.f-links a:hover{{color:var(--fg)}}
.f-copy{{font-size:.73rem;color:var(--dim)}}
@media(max-width:768px){{nav{{padding:1rem 1.5rem}}.nav-links{{display:none}}footer{{flex-direction:column;text-align:center}}}}
</style>
</head>
<body>

<div id="loader">
  <div class="l-bar"></div>
  <div class="l-txt">Loading</div>
</div>
<div id="cur"></div>
<div id="cur-r"></div>

<nav id="nav">
  <a class="nav-logo" href="#">{brand}</a>
  <ul class="nav-links">
    <li><a href="#items">{t["section1"]}</a></li>
    <li><a href="#features">{t["section2"]}</a></li>
    <li><a href="#about">About</a></li>
    <li><a href="#contact">Contact</a></li>
  </ul>
</nav>

<section class="hero" id="home">
  <div class="hero-bg"></div>
  <div class="hero-noise"></div>
  <div class="hero-inner">
    <span class="eyebrow">{t["eyebrow"]}</span>
    <h1 class="display">
      {t["hero_h1_line1"]}<br>
      <em>{t["hero_h1_line2"]}</em>
    </h1>
    <p class="hero-p">{t["hero_sub"]}</p>
    <a href="#items" class="btn">
      {t["cta"]}
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
    </a>
  </div>
</section>

<section id="items" class="section bg2">
  <span class="s-label reveal">{t["section1"]}</span>
  <h2 class="s-title reveal">{t["section1_sub"]}</h2>
  <div class="cards">{cards_html}</div>
</section>

<section id="features" class="section">
  <span class="s-label reveal">{t["section2"]}</span>
  <h2 class="s-title reveal">{t["section2_sub"]}</h2>
  <div class="feat-grid">
    <div class="feat reveal"><div class="feat-n">01</div><h3>Uncompromising Quality</h3><p>Every element selected with intention. Standards that exceed industry norms by design.</p></div>
    <div class="feat reveal"><div class="feat-n">02</div><h3>Heritage & Innovation</h3><p>Decades of expertise fused with forward-thinking methods. Respect for tradition; hunger for the new.</p></div>
    <div class="feat reveal"><div class="feat-n">03</div><h3>Limited Availability</h3><p>We believe in fewer, better. Each offering is deliberately limited to preserve its meaning.</p></div>
    <div class="feat reveal"><div class="feat-n">04</div><h3>Lifetime Partnership</h3><p>Our relationship doesn't end at purchase. We stand behind everything, indefinitely.</p></div>
  </div>
</section>

<section id="about" class="section bg2" style="text-align:center">
  <span class="s-label reveal">Our Story</span>
  <h2 class="s-title reveal" style="max-width:700px;margin:0 auto 1.5rem">Built for<br><em style="font-style:italic;color:var(--acc)">Eternity</em></h2>
  <p class="reveal" style="max-width:580px;margin:0 auto 2.5rem;color:var(--dim);line-height:1.85;font-size:1.05rem">
    True excellence is invisible to the untrained eye. It lives in the details — the weight, the finish, the silence. We obsess so you don't have to.
  </p>
  <a href="#contact" class="btn reveal" style="margin:0 auto">Get in Touch</a>
</section>

<footer id="contact">
  <div class="f-brand">{brand}</div>
  <div class="f-links">
    <a href="#">Instagram</a>
    <a href="#">LinkedIn</a>
    <a href="#">Contact</a>
    <a href="#">Privacy</a>
  </div>
  <div class="f-copy">© {yr} {topic.title()}. Built by A.L.I</div>
</footer>

<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/ScrollTrigger.min.js"></script>
<script>
// Loader
window.addEventListener('load',()=>setTimeout(()=>document.getElementById('loader').classList.add('gone'),900));

// Cursor
const cur=document.getElementById('cur'),ring=document.getElementById('cur-r');
let mx=0,my=0,rx=0,ry=0;
document.addEventListener('mousemove',e=>{{mx=e.clientX;my=e.clientY;cur.style.left=mx+'px';cur.style.top=my+'px'}});
(function loop(){{rx+=(mx-rx)*.1;ry+=(my-ry)*.1;ring.style.left=rx+'px';ring.style.top=ry+'px';requestAnimationFrame(loop)}})();
document.querySelectorAll('a,button,.card').forEach(el=>{{
  el.addEventListener('mouseenter',()=>{{cur.style.width='18px';cur.style.height='18px';ring.style.width='56px';ring.style.height='56px';ring.style.opacity='1'}});
  el.addEventListener('mouseleave',()=>{{cur.style.width='10px';cur.style.height='10px';ring.style.width='36px';ring.style.height='36px';ring.style.opacity='.5'}});
}});

// Nav scroll
const nav=document.getElementById('nav');
let lastY=0;
window.addEventListener('scroll',()=>{{const y=window.scrollY;nav.classList.toggle('solid',y>50);lastY=y}});

// GSAP ScrollTrigger reveals
gsap.registerPlugin(ScrollTrigger);
gsap.utils.toArray('.reveal').forEach(el=>{{
  gsap.fromTo(el,{{opacity:0,y:50}},{{
    opacity:1,y:0,duration:1,ease:'power3.out',
    scrollTrigger:{{trigger:el,start:'top 86%',toggleActions:'play none none none'}}
  }});
}});

// Card 3D tilt
document.querySelectorAll('.card').forEach(c=>{{
  c.addEventListener('mousemove',e=>{{
    const r=c.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
    c.style.transform=`perspective(700px) rotateY(${{x*8}}deg) rotateX(${{-y*8}}deg)`;
    c.style.transition='transform .05s';
  }});
  c.addEventListener('mouseleave',()=>{{c.style.transform='';c.style.transition='transform .5s ease'}});
}});

// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(a=>{{
  a.addEventListener('click',e=>{{e.preventDefault();document.querySelector(a.getAttribute('href'))?.scrollIntoView({{behavior:'smooth'}})}});
}});
</script>
</body>
</html>"""


# ── Main Entry ─────────────────────────────────────────────────────────────────

def website_builder(parameters: dict, player=None, speak=None) -> str:
    topic  = parameters.get("topic", "luxury brand website")
    style  = parameters.get("style", "award-winning minimalist")
    pages  = parameters.get("pages") or ["index"]
    if isinstance(pages, str):
        pages = [p.strip() for p in pages.split(",")]

    category = _classify_topic(topic)
    # Force variant if requested, otherwise pick randomly — ensures every build looks different
    forced_variant = parameters.get("variant", "").strip().lower()
    if forced_variant:
        variant = next((v for v in LAYOUT_VARIANTS if v["id"] == forced_variant), None)
    else:
        variant = None
    if variant is None:
        variant = random.choice(LAYOUT_VARIANTS)

    # Use timestamp in dir so each build is fresh, never overwrites previous
    ts   = time.strftime("%H%M%S")
    slug = re.sub(r'[^a-z0-9]+', '_', topic.lower())[:30]
    base = Path(parameters.get("output_dir") or
                Path.home() / "Desktop" / "ali_sites" / f"{slug}_{variant['id']}_{ts}")
    base.mkdir(parents=True, exist_ok=True)

    log = BuildLog(base / "build_log.txt")

    def say(msg):
        if speak:
            try: speak(msg)
            except Exception: pass
        if player:
            try: player.write_log(f"WEB: {msg}")
            except Exception: pass

    # Load API key
    try:
        api_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        api_key  = json.loads(api_path.read_text())["gemini_api_key"]
    except Exception as e:
        return f"Cannot build — API key error: {e}"

    ref_urls = INDUSTRY_REFS.get(category, INDUSTRY_REFS["default"])
    log.add(f"Topic: {topic} | Category: {category} | Style: {style}")
    log.add(f"Layout variant: {variant['name']}")
    log.add(f"Reference sites: {ref_urls}")

    say(f"On it, Ali. This is a {category} website, layout: {variant['name']}. "
        f"Visiting {len(ref_urls)} real industry sites for fresh inspiration.")

    # ── Phase 1: Screenshot reference sites ──
    log.add("═══ PHASE 1: VISITING INDUSTRY REFERENCE SITES ═══")
    try:
        screenshots = asyncio.run(_screenshot_sites(ref_urls, log))
    except Exception as e:
        log.add(f"Screenshot phase error: {e}")
        screenshots = []

    # ── Phase 2: Design fusion ──
    log.add("═══ PHASE 2: FUSING DESIGN DNA ═══")
    say(f"Analyzed {len(screenshots)} sites. Now fusing their design DNA into a unique brief...")
    brief = _fuse_designs(screenshots, topic, style, category, api_key, log)
    log.add("Design fusion complete. Key decisions:")
    for ln in brief.split('\n')[:6]:
        if ln.strip():
            log.add(f"  {ln.strip()[:100]}")

    # ── Phase 3: Generate HTML ──
    log.add(f"═══ PHASE 3: GENERATING [{variant['name'].upper()}] LAYOUT ═══")
    say(f"Generating a {variant['name']} layout — this is one of 6 different design approaches, "
        f"so it will look genuinely different. 30-90 seconds...")
    files = _generate_html(topic, style, pages, brief, category, screenshots, api_key, log, variant)

    # ── Phase 4: Validate & Write ──
    log.add("═══ PHASE 4: VALIDATING & WRITING FILES ═══")
    written = []

    if files:
        for fname, content in files.items():
            issues = _validate_html(content)
            if issues:
                log.add(f"⚠️  {fname}: {', '.join(issues)} — using category fallback")
                content = _build_fallback(topic, style, category)
            out = base / fname
            out.write_text(content, encoding="utf-8")
            written.append(fname)
            log.add(f"✅ Wrote {fname} ({len(content):,} chars)")
    else:
        log.add("No valid files from Gemini — using category-specific fallback")

    # Ensure index.html always exists
    if "index.html" not in written:
        html_files = [f for f in written if f.endswith(".html")]
        if html_files:
            content = (base / html_files[0]).read_text(encoding="utf-8")
            (base / "index.html").write_text(content, encoding="utf-8")
            written.insert(0, "index.html")
            log.add(f"Copied {html_files[0]} → index.html")
        else:
            log.add(f"Writing {category} category fallback template")
            html = _build_fallback(topic, style, category)
            (base / "index.html").write_text(html, encoding="utf-8")
            written.insert(0, "index.html")
            log.add(f"Wrote fallback ({len(html):,} chars)")

    # Emergency safety check
    idx_path = base / "index.html"
    if not idx_path.exists() or idx_path.stat().st_size < 1000:
        html = _build_fallback(topic, style, category)
        idx_path.write_text(html, encoding="utf-8")
        log.add("Emergency fallback written")

    # ── Phase 5: Serve, Verify, Open ──
    log.add("═══ PHASE 5: SERVING & VERIFYING ═══")
    port = _find_free_port()
    _serve(str(base), port)
    url = f"http://localhost:{port}/index.html"
    log.add(f"Server started on :{port} — verifying HTTP 200...")

    ok = _verify_server(url, retries=12, delay=0.4)
    if not ok:
        port = _find_free_port(start=port + 1)
        _serve(str(base), port)
        url = f"http://localhost:{port}/index.html"
        ok = _verify_server(url, retries=10, delay=0.5)

    status_str = "✅ HTTP 200 confirmed" if ok else "⚠️ could not verify — opening anyway"
    log.add(f"Server status: {status_str}")
    _open_browser(url)
    log.add(f"Opened in browser: {url}")
    log.add("═══ BUILD COMPLETE ═══")

    other_variants = [v["name"] for v in LAYOUT_VARIANTS if v["id"] != variant["id"]]
    say(f"Done, Ali! Your {topic} website — {variant['name']} layout — is {'verified' if ok else 'open'} in the browser. "
        f"I researched real {category} brand sites and fused their design DNA. "
        f"Don't like this layout? Say 'build it again' and I'll try a completely different one. "
        f"Other available layouts: {', '.join(other_variants[:3])}.")

    return (f"Website: {url} | {'OK' if ok else 'CHECK'} | "
            f"Files: {', '.join(written)} | Category: {category} | "
            f"Log: {base / 'build_log.txt'}")
