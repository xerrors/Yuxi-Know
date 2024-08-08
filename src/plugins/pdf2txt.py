import os
import fitz  # fitz就是pip install PyMuPDF
import cv2
from copy import deepcopy
from tqdm import tqdm


def pdf2txt(pdf_path, return_text=False):
    from paddleocr import PPStructure, save_structure_res
    from paddleocr.ppstructure.recovery.recovery_to_doc import sorted_layout_boxes, convert_info_docx
    output_dir = os.path.join('tmp', 'pdf2txt', os.path.basename(pdf_path).split('.')[0])
    os.makedirs(output_dir, exist_ok=True)

    table_engine = PPStructure(recovery=True, lang='ch')

    imgs = []
    img_dir = os.path.join(output_dir, 'imgs')
    if not os.path.exists(img_dir):
        os.makedirs(img_dir)
        pdfDoc = fitz.open(pdf_path)
        totalPage = pdfDoc.page_count
        for pg in tqdm(range(totalPage), desc='to imgs', ncols=100):
            page = pdfDoc[pg]
            rotate = int(0)
            zoom_x = 2
            zoom_y = 2
            mat = fitz.Matrix(zoom_x, zoom_y).prerotate(rotate)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_filename = os.path.join(img_dir, f'images_{pg+1}.png')
            pix.save(img_filename)  # os.sep
            imgs.append(img_filename)
    else:
        img_names = sorted(os.listdir(img_dir))
        imgs = [os.path.join(img_dir, img_name) for img_name in img_names]

    respath = os.path.join(output_dir, 'res.txt')

    text = []
    for img_name in tqdm(imgs, desc='to txt', ncols=100):
        img = cv2.imread(img_name)
        result = table_engine(img)

        save_structure_res(result, output_dir, "structure_result")

        res = sorted_layout_boxes(result, img.shape[1])

        try:
            convert_info_docx(img, res, output_dir, "info")
        except Exception as e:
            print(f"Exception occurred while converting to DOCX: {e}")
            continue  # Skip this image if conversion fails

        for line in res:
            line.pop('img') # okk
            for pra in line['res']:
                if isinstance(pra, dict) and 'text' in pra:
                    text.append(pra['text'])
                else:
                    continue  # 如果不是字典或者缺少 'text' 键，跳过当前循环
            text.append('\n')

    whole_text = '\n'.join(text)
    with open(respath, 'w', encoding='utf-8') as f:
        f.write(whole_text)

    if return_text:
        return whole_text

    return respath

if __name__ == "__main__":
    pdf_path = r'data/file/焙烤食品工艺学.pdf'
    print(pdf2txt(pdf_path))
