# The Village That Sailed the Sky

make.fun ai-excited-01 entry. A pure-Python (standard library only) program
that draws a layered illustrated poster — a floating village with glowing
houses and a waterfall pouring into a sea of clouds, a large sailing ship
flying free in front of a sunrise, a small distant ship for scale, birds
and light rays — and writes it to `/output/entry.png` (1024×1024 PNG).

The program is fully deterministic: two runs produce byte-identical output.
Set `OUTPUT_PATH` to override the output location for local verification.

Run: `python3 main.py`
