"""공유 미리보기 썸네일(web/public/og.png, 1200x630) 생성. 로고와 같은 종 모양 곡선을 그린다. 숫자는 매일 바뀌므로 넣지 않는다.
  python tools/make_og.py    (글꼴: Windows 맑은 고딕)"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "og.png"
FB, FR = "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf"
NAVY, TRACK, ORANGE, BLUE, WHITE, MUTED = "#1d2a44", "#3b4a68", "#ec6a2e", "#2a78d6", "#ffffff", "#aab4c6"
W, H, S = 1200, 630, 2


def bell(x, cx, sd):
    return math.exp(-0.5 * ((x - cx) / sd) ** 2)


def main():
    img = Image.new("RGB", (W * S, H * S), NAVY)
    d = ImageDraw.Draw(img)
    cx, base, top, sd = 330, 470, 190, 80  # 종 모양: 중심 x, 바닥 y, 꼭대기 y, 표준편차
    xs = [cx - 250 + i * 2 for i in range(251)]
    pts = [(x, base - (base - top) * bell(x, cx, sd)) for x in xs]
    # 채우기: 전체 회청색, 양쪽 꼬리 색
    def region(x0, x1, color):
        poly = [(x * S, y * S) for x, y in pts if x0 <= x <= x1]
        if len(poly) > 1:
            poly = [(poly[0][0], base * S)] + poly + [(poly[-1][0], base * S)]
            d.polygon(poly, fill=color)
    region(cx - 250, cx + 250, TRACK)
    region(cx + 105, cx + 250, ORANGE)
    region(cx - 250, cx - 105, BLUE)
    d.line([(x * S, y * S) for x, y in pts], fill=WHITE, width=9 * S, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([(x - 4.5) * S, (y - 4.5) * S, (x + 4.5) * S, (y + 4.5) * S], fill=WHITE)
    for y in range(top - 14, base, 22):  # 현재 환율 점선
        d.line([(cx * S, y * S), (cx * S, (y + 11) * S)], fill=WHITE, width=5 * S)
    d.rounded_rectangle([(cx - 250) * S, (base + 22) * S, (cx + 250) * S, (base + 34) * S], radius=6 * S, fill=TRACK)
    f1 = ImageFont.truetype(FB, 112 * S); f2 = ImageFont.truetype(FR, 40 * S); f3 = ImageFont.truetype(FR, 28 * S)
    d.text((660 * S, 190 * S), "FX ODDS", font=fit("FX ODDS", 112, maxw) if False else f1, fill=WHITE)
    d.text((664 * S, 340 * S), "환율의 확률과 압력을 읽다", font=f2, fill=WHITE)
    def fit(text, size, maxw):  # 오른쪽 여백 안에 들어오도록 글자 크기를 줄인다
        while size > 16:
            f = ImageFont.truetype(FR, size * S)
            if d.textlength(text, font=f) <= maxw * S:
                return f
            size -= 1
        return f
    maxw = W - 664 - 56
    d.text((664 * S, 410 * S), "7일·30일 확률 전망 · 뉴스 압력 · 동조화 레이더", font=fit("7일·30일 확률 전망 · 뉴스 압력 · 동조화 레이더", 28, maxw), fill=MUTED)
    d.text((664 * S, 460 * S), "주황 = 원화 약세 꼬리 · 파랑 = 원화 강세 꼬리", font=fit("주황 = 원화 약세 꼬리 · 파랑 = 원화 강세 꼬리", 28, maxw), fill=MUTED)
    img = img.resize((W, H), Image.LANCZOS)
    img.save(OUT, optimize=True)
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
