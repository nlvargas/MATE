"""
MATE architecture diagram generator (v2): adds an Instructor actor above
the React SPA, enlarges the React SPA box and the four async-path
("green"/teal) boxes, and recolors the React SPA box to React's brand
cyan-blue. Rewritten as a small node/edge system (rather than hand-tuned
absolute coordinates) so sizes/positions stay consistent when one box
changes.
"""
import subprocess

W = 1320

# -------------------- icon glyphs (white stroke, on a colored circle) --------------------

def icon_person(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round">'
            f'<circle cx="11" cy="7" r="4.2"/>'
            f'<path d="M2.5 21 C2.5 14.5 6.5 12 11 12 C15.5 12 19.5 14.5 19.5 21"/></g>')

def icon_browser(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="2" width="20" height="18" rx="2.5"/>'
            f'<line x1="1" y1="7.5" x2="21" y2="7.5"/>'
            f'<circle cx="4.2" cy="4.7" r="0.6" fill="white"/><circle cx="6.4" cy="4.7" r="0.6" fill="white"/></g>')

def icon_bucket(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"><ellipse cx="11" cy="5" rx="8" ry="2.3"/>'
            f'<path d="M3 5 L5.3 19.5 Q11 21.5 16.7 19.5 L19 5"/></g>')

def icon_gateway(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"><path d="M2 3 H20 L13.5 12 V19 L8.5 21 V12 Z"/></g>')

def icon_lambda(ccx, ccy):
    return f'<text x="{ccx}" y="{ccy+7}" text-anchor="middle" font-family="Georgia, serif" font-size="20" fill="white">&#955;</text>'

def icon_gear(ccx, ccy):
    return (f'<g transform="translate({ccx},{ccy})" stroke="white" stroke-width="1.5" fill="none" stroke-linecap="round">'
            f'<rect x="-5" y="-5" width="10" height="10" rx="1.5"/>'
            f'<line x1="-6" y1="-8" x2="-6" y2="-5"/><line x1="-6" y1="8" x2="-6" y2="5"/>'
            f'<line x1="-8" y1="-6" x2="-5" y2="-6"/><line x1="8" y1="-6" x2="5" y2="-6"/>'
            f'<line x1="0" y1="-8" x2="0" y2="-5"/><line x1="0" y1="8" x2="0" y2="5"/>'
            f'<line x1="-8" y1="0" x2="-5" y2="0"/><line x1="8" y1="0" x2="5" y2="0"/>'
            f'<line x1="6" y1="-8" x2="6" y2="-5"/><line x1="6" y1="8" x2="6" y2="5"/>'
            f'<line x1="-8" y1="6" x2="-5" y2="6"/><line x1="8" y1="6" x2="5" y2="6"/></g>')

def icon_plane(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"><path d="M2 12 L21 3 L13 20 L10.5 12.5 Z"/>'
            f'<line x1="10.5" y1="12.5" x2="21" y2="3"/></g>')

def icon_server(ccx, ccy):
    tx, ty = ccx - 10, ccy - 10.5
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.3" fill="none">'
            f'<rect x="0" y="0" width="20" height="5" rx="1"/><circle cx="3" cy="2.5" r="0.7" fill="white"/>'
            f'<rect x="0" y="7" width="20" height="5" rx="1"/><circle cx="3" cy="9.5" r="0.7" fill="white"/>'
            f'<rect x="0" y="14" width="20" height="5" rx="1"/><circle cx="3" cy="16.5" r="0.7" fill="white"/></g>')

def icon_grid(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="1" width="20" height="20" rx="2"/>'
            f'<line x1="1" y1="8" x2="21" y2="8"/><line x1="1" y1="14.5" x2="21" y2="14.5"/>'
            f'<line x1="8" y1="1" x2="8" y2="21"/><line x1="14.5" y1="1" x2="14.5" y2="21"/></g>')

def icon_envelope(ccx, ccy):
    tx, ty = ccx - 11, ccy - 11
    return (f'<g transform="translate({tx},{ty})" stroke="white" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3" width="20" height="15" rx="2"/>'
            f'<path d="M1.5 4 L11 12.5 L20.5 4"/></g>')


# -------------------- node rendering --------------------

class Node:
    def __init__(self, cx, top, w, h, fill, stroke, icon_fn, title, subtitle=None):
        self.cx, self.top, self.w, self.h = cx, top, w, h
        self.fill, self.stroke, self.icon_fn = fill, stroke, icon_fn
        self.title, self.subtitle = title, subtitle

    @property
    def left(self):
        return self.cx - self.w / 2

    @property
    def right(self):
        return self.cx + self.w / 2

    @property
    def bottom(self):
        return self.top + self.h

    @property
    def ccy(self):
        return self.top + self.h / 2

    def svg(self):
        x, y = self.left, self.top
        ccx = x + 40
        ccy = self.ccy
        tx = ccx + 34
        parts = [
            f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{self.w:.1f}" height="{self.h:.1f}" rx="14" '
            f'fill="{self.fill}" stroke="{self.stroke}" stroke-width="2"/>',
            f'<circle cx="{ccx:.1f}" cy="{ccy:.1f}" r="20" fill="{self.stroke}"/>',
            self.icon_fn(ccx, ccy),
            f'<text x="{tx:.1f}" y="{ccy-6:.1f}" font-family="Helvetica, Arial, sans-serif" font-size="16" '
            f'font-weight="600" fill="#0f172a">{self.title}</text>',
        ]
        if self.subtitle:
            parts.append(
                f'<text x="{tx:.1f}" y="{ccy+15:.1f}" font-family="Helvetica, Arial, sans-serif" font-size="12.5" '
                f'fill="#475569">{self.subtitle}</text>'
            )
        parts.append('</g>')
        return "".join(parts)


def arrow_label(x, y, text, anchor="middle"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="Helvetica, Arial, sans-serif" '
            f'font-size="12.5" fill="#334155">{text}</text>')


def polyline(points):
    pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    return f'<polyline points="{pts}" fill="none" stroke="#334155" stroke-width="2" marker-end="url(#arrowhead)"/>'


def line(x1, y1, x2, y2):
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#334155" '
            f'stroke-width="2" marker-end="url(#arrowhead)"/>')


# -------------------- colors --------------------

REACT_FILL, REACT_STROKE = "#ecfeff", "#0891b2"       # React's brand cyan-blue (was generic blue-600)
PURPLE_FILL, PURPLE_STROKE = "#f5f3ff", "#7c3aed"      # AWS internals
AMBER_FILL, AMBER_STROKE = "#fffbeb", "#d97706"        # sync CP-SAT solve
TEAL_FILL, TEAL_STROKE = "#f0fdfa", "#0d9488"          # async path
GRAY_FILL, GRAY_STROKE = "#f1f5f9", "#475569"          # email
ACTOR_STROKE = "#475569"

# -------------------- layout --------------------

STD_W, STD_H = 260, 70          # unresized boxes (S3, API GW, Lambda, CP-SAT solve, email pill uses its own)
BIG_W, BIG_H = 290, 82          # enlarged: React SPA + the 4 async/teal boxes

user = {"cx": 660, "cy": 55, "r": 18}
spa_top = 120

spa = Node(660, spa_top, BIG_W, BIG_H, REACT_FILL, REACT_STROKE, icon_browser,
           "React SPA", "Setup &#8594; Upload &#8594; Configure &#8594; Results")

aws_dash_top = spa.bottom + 65
aws_dash_h = 300
s3 = Node(350, aws_dash_top + 25, STD_W, STD_H, PURPLE_FILL, PURPLE_STROKE, icon_bucket,
          "S3 bucket", "Static frontend assets")
apigw = Node(960, aws_dash_top + 25, STD_W, STD_H, PURPLE_FILL, PURPLE_STROKE, icon_gateway,
             "API Gateway", "Routes requests to the app")
lambda_ = Node(960, aws_dash_top + 155, STD_W, STD_H, PURPLE_FILL, PURPLE_STROKE, icon_lambda,
               "Lambda", "Runs the web application")

diamond_top_y = aws_dash_top + aws_dash_h + 25
diamond_cy = diamond_top_y + 60
diamond_bottom_y = diamond_cy + 60

row1_top = diamond_bottom_y + 80
cpsat = Node(660, row1_top, STD_W, STD_H, AMBER_FILL, AMBER_STROKE, icon_gear,
             "CP-SAT solve", "Runs in-request")
submit = Node(960, row1_top, BIG_W, BIG_H, TEAL_FILL, TEAL_STROKE, icon_plane,
              "Package &amp; submit job", "Over SSH")

slurm_top = row1_top + 120
slurm = Node(960, slurm_top, BIG_W, BIG_H, TEAL_FILL, TEAL_STROKE, icon_server,
             "University Slurm cluster", "Headless batch compute")

gurobi_top = slurm_top + 120
gurobi = Node(960, gurobi_top, BIG_W, BIG_H, TEAL_FILL, TEAL_STROKE, icon_gear,
              "Gurobi solve", "Runs as a batch job")

sheet_top = gurobi_top + 120
sheet = Node(960, sheet_top, BIG_W, BIG_H, TEAL_FILL, TEAL_STROKE, icon_grid,
             "Build results spreadsheet", None)

email_top = sheet_top + 120
email = Node(960, email_top, 220, 56, GRAY_FILL, GRAY_STROKE, icon_envelope,
             "Email to instructor", None)

H = email.bottom + 24

# -------------------- assemble --------------------

svg = []
svg.append(f'<svg viewBox="0 0 {W} {H:.0f}" xmlns="http://www.w3.org/2000/svg" role="img"\n'
           f'  aria-label="MATE architecture: an instructor uses a React single-page app, which talks to an AWS '
           f'deployment (API Gateway, Lambda, S3) behind Zappa; small rosters solve synchronously with CP-SAT and '
           f'return JSON directly, while large rosters are packaged and sent over SSH to a university Slurm cluster '
           f'for a headless Gurobi batch solve, ending in an emailed results spreadsheet.">')
svg.append('<defs><marker id="arrowhead" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="#334155"/></marker></defs>')
svg.append(f'<rect x="0" y="0" width="{W}" height="{H:.0f}" fill="#ffffff"/>')

# ---- arrows (drawn first, boxes drawn on top of their endpoints) ----

# Instructor -> SPA
svg.append(line(user["cx"], user["cy"] + user["r"], spa.cx, spa.top))

# SPA -> S3 (GET static assets)
mid_y = spa.bottom + 22
svg.append(polyline([(spa.cx, spa.bottom), (spa.cx, mid_y), (s3.cx, mid_y), (s3.cx, s3.top)]))
svg.append(arrow_label(s3.cx, mid_y - 8, "GET static assets"))

# SPA -> API Gateway (upload roster / run solve)
mid_y2 = spa.bottom + 44
svg.append(polyline([(spa.cx, spa.bottom), (spa.cx, mid_y2), (apigw.cx, mid_y2), (apigw.cx, apigw.top)]))
svg.append(arrow_label(apigw.cx, mid_y2 - 10, "upload roster / run solve"))

# API Gateway -> Lambda
svg.append(line(apigw.cx, apigw.bottom, lambda_.cx, lambda_.top))

# Lambda -> decision diamond
svg.append(line(lambda_.cx, lambda_.bottom, 960, diamond_top_y))

# decision -> CP-SAT solve (yes / sync)
svg.append(polyline([(960 - 150, diamond_cy), (cpsat.cx, diamond_cy), (cpsat.cx, cpsat.top)]))
svg.append(arrow_label(cpsat.cx, diamond_cy - 8, "yes: small model (sync path)"))

# decision -> Package & submit (no / async)
svg.append(line(960, diamond_bottom_y, submit.cx, submit.top))
svg.append(arrow_label(submit.cx, diamond_bottom_y + 32, "no: large model (async path)"))

# CP-SAT solve -> SPA (JSON response), routed around the left margin
json_y = cpsat.ccy
svg.append(polyline([(cpsat.left, json_y), (120, json_y), (120, spa.ccy), (spa.left, spa.ccy)]))
svg.append(arrow_label(110, spa.ccy - 10, "JSON response"))

# async chain, straight verticals
svg.append(line(submit.cx, submit.bottom, slurm.cx, slurm.top))
svg.append(line(slurm.cx, slurm.bottom, gurobi.cx, gurobi.top))
svg.append(line(gurobi.cx, gurobi.bottom, sheet.cx, sheet.top))
svg.append(line(sheet.cx, sheet.bottom, email.cx, email.top))

# ---- nodes ----

# Instructor actor (no box, just badge + label, matching node style)
svg.append(f'<circle cx="{user["cx"]}" cy="{user["cy"]}" r="{user["r"]}" fill="{ACTOR_STROKE}"/>')
svg.append(icon_person(user["cx"], user["cy"]))
svg.append(arrow_label(user["cx"], user["cy"] - user["r"] - 8, "Instructor"))

svg.append(spa.svg())

svg.append(f'<rect x="{s3.left-80:.1f}" y="{aws_dash_top:.1f}" width="1040" height="{aws_dash_h}" rx="16" '
           f'fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="6,5"/>')
svg.append(f'<text x="{s3.left-62:.1f}" y="{aws_dash_top-10:.1f}" font-family="Helvetica, Arial, sans-serif" '
           f'font-size="13" font-weight="600" fill="#64748b">AWS &#8212; deployed via Zappa</text>')

svg.append(s3.svg())
svg.append(apigw.svg())
svg.append(lambda_.svg())

svg.append(f'<polygon points="960,{diamond_top_y:.1f} 1110,{diamond_cy:.1f} 960,{diamond_bottom_y:.1f} '
           f'810,{diamond_cy:.1f}" fill="#f8fafc" stroke="#334155" stroke-width="2"/>')
svg.append(f'<text x="960" y="{diamond_cy-9:.1f}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
           f'font-size="13.5" font-weight="600" fill="#0f172a">Estimated variable count within</text>')
svg.append(f'<text x="960" y="{diamond_cy+9:.1f}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
           f'font-size="13.5" font-weight="600" fill="#0f172a">the synchronous-solve threshold?</text>')

svg.append(cpsat.svg())
svg.append(submit.svg())
svg.append(slurm.svg())
svg.append(gurobi.svg())
svg.append(sheet.svg())

svg.append(f'<rect x="{email.left:.1f}" y="{email.top:.1f}" width="{email.w}" height="{email.h}" rx="28" '
           f'fill="{GRAY_FILL}" stroke="{GRAY_STROKE}" stroke-width="2"/>')
ecx = email.left + 34
svg.append(f'<circle cx="{ecx:.1f}" cy="{email.ccy:.1f}" r="18" fill="{GRAY_STROKE}"/>')
svg.append(icon_envelope(ecx, email.ccy))
svg.append(f'<text x="{ecx+28:.1f}" y="{email.ccy+5:.1f}" font-family="Helvetica, Arial, sans-serif" '
           f'font-size="15" font-weight="600" fill="#0f172a">Email to instructor</text>')

svg.append('</svg>')

out = "\n".join(svg)
with open("architecture.svg", "w") as f:
    f.write(out)
print("wrote architecture.svg", len(out), "bytes, height", H)
