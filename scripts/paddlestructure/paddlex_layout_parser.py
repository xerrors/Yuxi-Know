
import requests
import json
import base64
import os
import time
from typing import Optional, Dict, Any




class PaddleXLayoutParser:
    """PaddleX 版面解析服务客户端"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
        self.endpoint = f"{self.base_url}/layout-parsing"

    def encode_file_to_base64(self, file_path: str) -> str:
        with open(file_path, 'rb') as file:
            encoded = base64.b64encode(file.read()).decode('utf-8')
            return encoded

    def _process_file_input(self, file_input: str) -> str:
        # 检查是否为本地文件路径
        if os.path.exists(file_input):
            print(f"📁 检测到本地文件: {file_input}")
            print(f"📏 文件大小: {os.path.getsize(file_input) / 1024 / 1024:.2f} MB")

            try:
                # 将本地文件编码为Base64
                encoded_content = self.encode_file_to_base64(file_input)
                print(f"✅ 文件已编码为Base64，长度: {len(encoded_content)} 字符")
                return encoded_content
            except Exception as e:
                print(f"❌ 文件编码失败: {e}")
                raise

        # 检查是否为URL
        elif file_input.startswith(('http://', 'https://')):
            print(f"🌐 检测到URL: {file_input}")
            return file_input

        # 否则假设为Base64编码内容
        else:
            print(f"📝 假设为Base64编码内容，长度: {len(file_input)} 字符")
            return file_input

    def layout_parsing(self,
            file_input: str,
            file_type: Optional[int] = None,
            use_textline_orientation: Optional[bool] = None,
            use_seal_recognition: Optional[bool] = None,
            use_table_recognition: Optional[bool] = None,
            use_formula_recognition: Optional[bool] = None,
            use_chart_recognition: Optional[bool] = None,
            use_region_detection: Optional[bool] = None,
            layout_threshold: Optional[float] = None,
            layout_nms: Optional[bool] = None,
            use_doc_orientation_classify: Optional[bool] = True,
            use_doc_unwarping: Optional[bool] = False,
            use_wired_table_cells_trans_to_html: Optional[bool] = True, # 是否启用无有线表单元格检测结果直转HTML，默认False，启用则直接基于有线表单元格检测结果的几何关系构建HTML。
            **kwargs) -> Dict[str, Any]:
        """
        调用版面解析API：https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/PP-StructureV3.html#22-python
        """
        # 处理文件输入：检测是否为本地文件路径
        processed_file_input = self._process_file_input(file_input)
        payload = {"file": processed_file_input}

        # 添加可选参数
        optional_params = {
            "fileType": file_type,
            "useDocOrientationClassify": use_doc_orientation_classify,
            "useDocUnwarping": use_doc_unwarping,
            "useTextlineOrientation": use_textline_orientation,
            "useSealRecognition": use_seal_recognition,
            "useTableRecognition": use_table_recognition,
            "useFormulaRecognition": use_formula_recognition,
            "useChartRecognition": use_chart_recognition,
            "useRegionDetection": use_region_detection,
            "layoutThreshold": layout_threshold,
            "layoutNms": layout_nms,
            "useWiredTableCellsTransToHtml": use_wired_table_cells_trans_to_html,
        }

        # 添加非空参数
        for key, value in optional_params.items():
            if value is not None:
                payload[key] = value

        # 添加其他kwargs参数
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=300
            )

            if response.status_code == 200:
                result = response.json()
                print("✅ 请求成功!")
                return result
            else:
                print("❌ 请求失败!")
                try:
                    error_result = response.json()
                    print(f"错误信息: {json.dumps(error_result, indent=2, ensure_ascii=False)}")
                    return error_result
                except:
                    print(f"响应内容: {response.text}")
                    return {"error": response.text, "status_code": response.status_code}

        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求异常: {e}")
            return {"error": str(e)}
        except Exception as e:
            print(f"❌ 其他异常: {e}")
            return {"error": str(e)}



def _parse_recognition_result(api_result: Dict[str, Any], file_path: str) -> Dict[str, Any]:
    # 基本信息
    parsed_result = {
        "success": True,
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "log_id": api_result.get("logId"),
        "total_pages": 0,
        "pages": [],
        "full_text": "",
        "summary": {}
    }

    result_data = api_result.get("result", {})
    layout_results = result_data.get("layoutParsingResults", [])
    data_info = result_data.get("dataInfo", {})

    # 数据信息
    parsed_result["total_pages"] = len(layout_results)
    parsed_result["document_info"] = {
        "type": data_info.get("type", "unknown"),
        "total_pages": data_info.get("numPages", len(layout_results)),
        "page_dimensions": data_info.get("pages", [])
    }

    # 统计信息
    total_elements = 0
    total_tables = 0
    total_formulas = 0
    total_charts = 0
    total_seals = 0
    all_text_content = []

    # 解析每页结果
    for page_index, page_result in enumerate(layout_results):
        page_info = {
            "page_number": page_index + 1,
            "content": {},
            "statistics": {}
        }

        # Markdown内容
        if "markdown" in page_result:
            markdown = page_result["markdown"]
            page_info["content"]["markdown_text"] = markdown.get("text", "")
            page_info["content"]["images"] = list(markdown.get("images", {}).keys())
            page_info["content"]["is_paragraph_start"] = markdown.get("isStart", False)
            page_info["content"]["is_paragraph_end"] = markdown.get("isEnd", False)

            # 收集文本内容
            if markdown.get("text"):
                all_text_content.append(markdown["text"])

        # 详细识别结果
        if "prunedResult" in page_result:
            pruned = page_result["prunedResult"]

            # 版面检测
            layout_detection = pruned.get("layout_detection", [])
            page_info["statistics"]["layout_elements"] = len(layout_detection)
            total_elements += len(layout_detection)

            # OCR结果
            ocr_result = pruned.get("ocr_result", [])
            page_info["statistics"]["ocr_elements"] = len(ocr_result)

            # 表格识别
            table_result = pruned.get("table_result", [])
            page_info["statistics"]["tables"] = len(table_result)
            total_tables += len(table_result)

            # 公式识别
            formula_result = pruned.get("formula_result", [])
            page_info["statistics"]["formulas"] = len(formula_result)
            total_formulas += len(formula_result)

            # 图表识别
            chart_result = pruned.get("chart_result", [])
            page_info["statistics"]["charts"] = len(chart_result)
            total_charts += len(chart_result)

            # 印章识别
            seal_result = pruned.get("seal_result", [])
            page_info["statistics"]["seals"] = len(seal_result)
            total_seals += len(seal_result)

            # 详细元素信息
            page_info["content"]["layout_elements"] = layout_detection
            page_info["content"]["ocr_elements"] = ocr_result
            page_info["content"]["tables"] = table_result
            page_info["content"]["formulas"] = formula_result
            page_info["content"]["charts"] = chart_result
            page_info["content"]["seals"] = seal_result

        parsed_result["pages"].append(page_info)

    # 汇总全文内容
    parsed_result["full_text"] = "\n\n".join(all_text_content)

    # 汇总统计信息
    parsed_result["summary"] = {
        "total_elements": total_elements,
        "total_tables": total_tables,
        "total_formulas": total_formulas,
        "total_charts": total_charts,
        "total_seals": total_seals,
        "total_characters": len(parsed_result["full_text"]),
        "average_elements_per_page": round(total_elements / max(1, len(layout_results)), 2)
    }

    return parsed_result


def analyze_document(file_path: str) -> Dict[str, Any]:

    # 检查文件是否存在
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"文件不存在: {file_path}",
            "file_path": file_path
        }

    # 初始化客户端
    client = PaddleXLayoutParser()

    # 判断文件类型
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext == '.pdf':
        file_type = 0
    elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
        file_type = 1
    else:
        return {
            "success": False,
            "error": f"不支持的文件类型: {file_ext}",
            "file_path": file_path
        }

    print(f"📄 开始分析文档: {os.path.basename(file_path)}")
    print(f"📏 文件大小: {os.path.getsize(file_path) / 1024 / 1024:.2f} MB")
    print(f"📋 文件类型: {'PDF' if file_type == 0 else '图片'}")

    try:
        # 调用API进行识别
        result = client.layout_parsing(file_input=file_path, file_type=file_type)

        # 检查API调用是否成功
        if result.get("errorCode") != 0:
            return {
                "success": False,
                "error": result.get("errorMsg", "API调用失败"),
                "file_path": file_path,
                "raw_result": result
            }

        # 解析结果
        analysis_result = _parse_recognition_result(result, file_path)
        return analysis_result

    except Exception as e:
        return {
            "success": False,
            "error": f"处理异常: {str(e)}",
            "file_path": file_path
        }
