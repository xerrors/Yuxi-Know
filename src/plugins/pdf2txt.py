import os
import fitz  # fitz就是pip install PyMuPDF
import cv2
from paddleocr import PPStructure, save_structure_res
from paddleocr.ppstructure.recovery.recovery_to_doc import sorted_layout_boxes, convert_info_docx
from copy import deepcopy
from tqdm import tqdm

table_engine = PPStructure(recovery=True, lang='ch')

def pdf2txt(pdfPath):
    imagePath = os.path.join('./imgs', os.path.basename(pdfPath).split('.')[0])
    if not os.path.exists(imagePath):
        os.makedirs(imagePath)
        pdfDoc = fitz.open(pdfPath)
        totalPage = pdfDoc.page_count
        for pg in tqdm(range(totalPage), desc='to imgs', ncols=100):
            page = pdfDoc[pg]
            rotate = int(0)
            zoom_x = 2
            zoom_y = 2
            mat = fitz.Matrix(zoom_x, zoom_y).prerotate(rotate)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(imagePath + '/' + f'images_{pg+1}.png')

    img_path = imagePath
    textPath = os.path.join('./txt', os.path.basename(pdfPath).split('.')[0])
    if not os.path.exists(textPath):
        os.makedirs(textPath)
    respath = os.path.join(textPath, 'res.txt')
    text = []
    imgs = sorted(os.listdir(img_path))
    for img_name in tqdm(imgs, desc='to txt', ncols=100):
        img = cv2.imread(os.path.join(img_path, img_name))
        result = table_engine(img)

        save_structure_res(result, textPath, os.path.basename(img_path).split('.')[0])

        h, w, _ = img.shape
        res = sorted_layout_boxes(result, w)

        try:
            convert_info_docx(img, res, textPath, os.path.basename(img_path).split('.')[0])
        except Exception as e:
            print(f"Exception occurred while converting to DOCX: {e}")
            continue  # Skip this image if conversion fails

        for line in res:
            line.pop('img')
            for pra in line['res']:
                if isinstance(pra, dict) and 'text' in pra:
                    text.append(pra['text'])
                else:
                    continue  # 如果不是字典或者缺少 'text' 键，跳过当前循环
            text.append('\n')

    with open(respath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text))

if __name__ == "__main__":
    pdfPath = r'ppp/焙烤食品工艺学.pdf'
    pdf2txt(pdfPath)
