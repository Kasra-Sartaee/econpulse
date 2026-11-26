# Reference images for the visual check

`tools/visual_check.py` renders the app's key screens from demo data at a fixed moment and compares
them with the PNGs in this folder; the [Visual check workflow](../../.github/workflows/visual.yml)
runs it on every pull request.

The images must come from CI's Windows runner, because fonts and display scaling differ between
machines. To set them up, or to accept an intended visual change:

1. Open the pull request's *Visual check* run and download its `visual` artifact.
2. Copy the `.png` files (not the `.diff.png` ones) into this folder and commit them.

Until this folder has images, the check renders the screens and uploads them, but has nothing to
compare against, so it can't fail.
