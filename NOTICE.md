# Attribution and distribution

Original application code is offered under GNU AGPL version 3. Copyright 2026 Abhijith Viswanathan. Developed with AI assistance.

Ultralytics YOLO11 and its pretrained detector weights use AGPL-3.0. The application supplies corresponding source and explicit setup tools. Pretrained detector and MobileNet backbone files are excluded from distributable source archives; download them from official sources with tools/setup_models.py.

Torchvision code is BSD-3-Clause (license retained). The ImageNet-trained backbone retains its upstream dataset provenance; the training images are not included. This project trained a separate linear classifier head, included as a small NumPy archive.

TrashNet by Gary Thung and Mindy Yang uses the MIT license, retained under licenses. The waste package includes six sample images with their exact original paths in samples/catalog.json. COCO annotations use CC BY 4.0; photos have individual Flickr licenses. COCO images are not included in public packages. Their original URLs and license IDs remain in the dataset manifest. Download only the examples needed for authorized local evaluation.

Third-party Python packages retain their respective licenses. Requirements files specify dependencies; no package source is vendored. See docs/model-and-data.md for model, dataset and documentation source links.
