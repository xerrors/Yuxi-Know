#! /bin/sh
source src/.env

# OCR 模型
huggingface-cli download SWHL/RapidOCR --local-dir ${MODEL_DIR}/SWHL/RapidOCR