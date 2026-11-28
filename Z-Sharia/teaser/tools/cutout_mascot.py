"""Cut the two mascot poses out of maskot_final.png (white background -> alpha).
Flood-fills near-white from the image border only, so the white eyes/whiskers
inside the silhouette stay opaque. Edge pixels get alpha by un-mixing from white."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage

src, outdir = sys.argv[1], sys.argv[2]
im = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
h, w, _ = im.shape
mn = im.min(axis=2)
near_white = mn > 200
# erode first so thin necks (e.g. a whisker tip touching the outside) don't leak
core = ndimage.binary_erosion(near_white, iterations=4, border_value=1)
lab, _ = ndimage.label(core)
border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
bg = np.isin(lab, list(border))
bg = ndimage.binary_dilation(bg, iterations=4) & near_white
# enclosed gaps of real background (between tail and arm) that are ringed by fur, not by the face mask
lab2, n2 = ndimage.label(near_white & ~bg)
for i in range(1, n2 + 1):
    m = lab2 == i
    ys, xs = np.where(m)
    ring = ndimage.binary_dilation(m, iterations=3) & ~m
    ring_mean = im[ring].mean(0)
    # tail/arm gap: medium-size blob, roughly as tall as wide, ringed by fur teal
    if 100 < m.sum() < 400 and (np.ptp(ys) + 1) / (np.ptp(xs) + 1) > 0.5 and ring_mean[0] < 100 and xs.min() > 500:
        bg |= m
# alpha: fully transparent bg, opaque fg; soften a 2px rim by un-mixing from white
alpha = np.where(bg, 0.0, 1.0)
rim = ndimage.binary_dilation(~bg, iterations=2) & bg
# for rim pixels estimate coverage from distance to white
cov = np.clip((255 - mn) / 255 * 3.0, 0, 1)
alpha = np.where(rim, cov, alpha)
rgb = im.copy()
a3 = np.maximum(alpha, 1e-3)[..., None]
un = (im - 255 * (1 - a3)) / a3
rgb = np.where(((alpha > 0) & (alpha < 1))[..., None], np.clip(un, 0, 255), im)
rgba = np.dstack([rgb, alpha * 255]).astype(np.uint8)
img = Image.fromarray(rgba, "RGBA")

def save(box, name):
    c = img.crop(box)
    bb = c.getbbox()
    c = c.crop(bb)
    c.save(f"{outdir}/{name}.png")
    print(name, c.size)

save((0, 0, 400, 400), "cat_head")
save((420, 0, 760, 400), "cat_jump")
