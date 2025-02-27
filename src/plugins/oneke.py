# readmore: https://github.com/zjunlp/DeepKE/blob/main/example/llm/OneKE.md
import os
import json
import torch
import dotenv
from transformers import (
    AutoConfig,
    AutoTokenizer,
    AutoModelForCausalLM,
    GenerationConfig,
    BitsAndBytesConfig
)

from src.utils import logger

dotenv.load_dotenv()

instruction_mapper = {
    'NERzh': "你是专门进行实体抽取的专家。请从input中抽取出符合schema定义的实体，不存在的实体类型返回空列表。请按照JSON字符串的格式回答。",
    'REzh': "你是专门进行关系抽取的专家。请从input中抽取出符合schema定义的关系三元组。请按照JSON字符串的格式回答。",
    'EEzh': "你是专门进行事件提取的专家。请从input中抽取出符合schema定义的事件，不存在的事件返回空列表，不存在的论元返回NAN，如果论元存在多值请返回列表。请按照JSON字符串的格式回答。",
    'EETzh': "你是专门进行事件提取的专家。请从input中抽取出符合schema定义的事件类型及事件触发词，不存在的事件返回空列表。请按照JSON字符串的格式回答。",
    'EEAzh': "你是专门进行事件论元提取的专家。请从input中抽取出符合schema定义的事件论元及论元角色，不存在的论元返回NAN或空字典，如果论元存在多值请返回列表。请按照JSON字符串的格式回答。",
    'KGzh': '你是一个图谱实体知识结构化专家。根据输入实体类型(entity type)的schema描述，从文本中抽取出相应的实体实例和其属性信息，不存在的属性不输出, 属性存在多值就返回列表，并输出为可解析的json格式。',
    'NERen': "You are an expert in named entity recognition. Please extract entities that match the schema definition from the input. Return an empty list if the entity type does not exist. Please respond in the format of a JSON string.",
    'REen': "You are an expert in relationship extraction. Please extract relationship triples that match the schema definition from the input. Return an empty list for relationships that do not exist. Please respond in the format of a JSON string.",
    'EEen': "You are an expert in event extraction. Please extract events from the input that conform to the schema definition. Return an empty list for events that do not exist, and return NAN for arguments that do not exist. If an argument has multiple values, please return a list. Respond in the format of a JSON string.",
    'EETen': "You are an expert in event extraction. Please extract event types and event trigger words from the input that conform to the schema definition. Return an empty list for non-existent events. Please respond in the format of a JSON string.",
    'EEAen': "You are an expert in event argument extraction. Please extract event arguments and their roles from the input that conform to the schema definition, which already includes event trigger words. If an argument does not exist, return NAN or an empty dictionary. Please respond in the format of a JSON string.",
    'KGen': 'You are an expert in structured knowledge systems for graph entities. Based on the schema description of the input entity type, you extract the corresponding entity instances and their attribute information from the text. Attributes that do not exist should not be output. If an attribute has multiple values, a list should be returned. The results should be output in a parsable JSON format.',
}

split_num_mapper = {
    'NER':6, 'RE':4, 'EE':4, 'EET':4, 'EEA':4, 'KG':1
}

class OneKE:

    def __init__(self, config=None):

        self.config = config
        model_name_or_path = config.model_local_paths.get('zjunlp/OneKE', "zjunlp/OneKE")
        logger.info(f"Loading KGC model OneKE from {model_name_or_path}")

        model_config = AutoConfig.from_pretrained(model_name_or_path, trust_remote_code=True)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, trust_remote_code=True)

        self.quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            llm_int8_threshold=6.0,
            llm_int8_has_fp16_weight=False,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

        self.generate_config = GenerationConfig(
            max_length=1024,
            max_new_tokens=512,
            return_dict_in_generate=True
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            config=model_config,
            device_map="auto",
            quantization_config=self.quantization_config,
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
        )
        self.model.eval()

    def construct_input(self, text, schema, task, language="zh", use_split=False):
        if use_split:
            split_num = split_num_mapper[task]
            if isinstance(schema, dict):
                schema_keys = list(schema.keys())
                schema_keys = [schema_keys[i:i+split_num] for i in range(0, len(schema_keys), split_num)]
                schema = [{k: schema[k] for k in keys} for keys in schema_keys]
            else:
                schema = [schema[i:i+split_num] for i in range(0, len(schema), split_num)]
        else:
            schema = [schema]

        sintructs = []
        for s in schema:
            sintruct = json.dumps({
                "instruction": instruction_mapper[task+language],
                "schema": s,
                "input": text,
            }, ensure_ascii=False)
            sintructs.append(sintruct)

        return sintructs

    def predict(self, text, schema, task, language="zh", use_split=False):
        sintructs = self.construct_input(text, schema, task, language, use_split)
        outputs = []
        for sintruct in sintructs:
            input_ids = self.tokenizer.encode(sintruct, return_tensors="pt").to(self.model.device)
            input_length = input_ids.size(1)

            generation_output = self.model.generate(
                input_ids=input_ids,
                generation_config=self.generate_config,
                pad_token_id=self.tokenizer.eos_token_id
            )
            generation_output = generation_output.sequences[0]
            generation_output = generation_output[input_length:]
            output = self.tokenizer.decode(generation_output, skip_special_tokens=True)

            outputs.append(output)

        return outputs

    def processing_text_to_kg(self, text_or_path, output_path):
        for chunk in read_and_process_chars(text_or_path):

            text = chunk
            schema = [
                {
                    "entity_type": "食品",
                    "attributes": {
                        "名称": "食品的名称，包括品牌名、通用名称或专业化学名",
                        "分类": "食品所属的类型，例如水果、蔬菜、肉类、谷物、调料、添加剂、益生菌等",
                        "成分": "食品的主要成分，详细列出包括天然成分、添加剂、保鲜剂、营养强化剂等",
                        "营养价值": "食品的营养成分，概括其提供的能量和主要营养素，如蛋白质、脂肪、碳水化合物、维生素和矿物质",
                        "加工方式": "食品的处理或制备方法，包括日常烹饪、加工处理及实验室制备方式等",
                        "作用或食用效果": "食品对健康或身体的影响，可能的功效或用途"
                    }
                }
            ]
            task = "KG"
            output = self.predict(text=text, schema=schema, task=task, language="zh")
            formatted_output = parse_and_format_output(output=output, task_type=task)

            with open(output_path, 'a+', encoding='utf-8') as f:
                for entry in formatted_output:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        print(f"预测结果已添加到 {output_path} 文件中。")
        return output_path

def read_and_process_chars(file_path, char_size=512, overlap_size=100):
    buffer = ""
    with open(file_path, 'r', encoding='utf-8') as file:
        while True:
            chunk = file.read(char_size)
            if not chunk:  # 文件读取完毕
                if buffer:
                    yield buffer
                break
            chunk = chunk.replace('\n', '').replace('\r', '')  # 去除换行符
            buffer += chunk
            while len(buffer) >= char_size:
                yield buffer[:char_size]
                buffer = buffer[char_size - overlap_size:]

def parse_and_format_output(output, task_type):
    formatted_output = []

    for entry in output:
        try:
            # Check if the entry is a valid JSON string
            if isinstance(entry, str) and entry.strip().startswith('{') and entry.strip().endswith('}'):
                parsed_entry = json.loads(entry)

                if task_type == "KG":
                    for entity_type, entities in parsed_entry.items():
                        for entity_name, attributes in entities.items():
                            for attribute_name, attribute_values in attributes.items():
                                if isinstance(attribute_values, list):
                                    for value in attribute_values:
                                        formatted_output.append({
                                            "h": entity_name,
                                            "t": value,
                                            "r": attribute_name
                                        })
                                else:
                                    formatted_output.append({
                                        "h": entity_name,
                                        "t": attribute_values,
                                        "r": attribute_name
                                    })
                elif task_type == "RE":
                    for relation_type, pairs in parsed_entry.items():
                        for pair in pairs:
                            formatted_output.append({
                                "h": pair["subject"],
                                "t": pair["object"],
                                "r": relation_type
                            })
            else:
                raise json.JSONDecodeError("Invalid JSON format", entry, 0)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e} - Skipping entry")
            continue
        except TypeError as e:
            print(f"TypeError: {e} - Skipping entry")
            continue
        except AttributeError as e:
            print(f"AttributeError: {e} - Skipping entry")
            continue

    return formatted_output


if __name__ == "__main__":
    oneke = OneKE()
    oneke.processing_text_to_kg("asdasdadadsad", 'kg.jsonl')

    file_path = ''
    output_path = ''
    text = ""
    task = "KG"
    for chunk in read_and_process_chars(file_path):

        text = chunk

        # schema = {
        #     "定义": "描述食品的起源、传统制作方法、文化象征意义或者描述食品或相关事物的定义或含义。包括食品的来源、特点及其在特定文化或背景下的意义。",
        #     "组成成分": "描述食品的组成部分或成分，包括主要成分、微量成分、添加剂等，揭示食品的化学或物理组成。",
        #     "功能": "描述食品或其成分的功能或作用，包括其对人体健康的影响、在烹饪中的用途、药用价值等。",
        #     "属性": "描述食品或其成分的特性或属性，揭示其独特的营养价值、口感特点、保存方式等，包括食品的营养价值、口感特点（如口感丰富、清淡等）、保存方式（如冷藏、冷冻、干燥等）",
        #     "种类": "描述食品或相关事物的种类或类别，揭示其分类体系、不同类型的特点及其在具体应用中的区别。"
        # }

        schema = [
            {
                "entity_type": "食品",
                "attributes": {
                    "名称": "食品的名称，包括品牌名、通用名称或专业化学名",
                    "分类": "食品所属的类型，例如水果、蔬菜、肉类、谷物、调料、添加剂、益生菌等",
                    "成分": "食品的主要成分，详细列出包括天然成分、添加剂、保鲜剂、营养强化剂等",
                    "营养价值": "食品的营养成分，概括其提供的能量和主要营养素，如蛋白质、脂肪、碳水化合物、维生素和矿物质",
                    "加工方式": "食品的处理或制备方法，包括日常烹饪、加工处理及实验室制备方式等",
                    "作用或食用效果": "食品对健康或身体的影响，可能的功效或用途"
                }
            }
        ]

        output = oneke.predict(text=text, schema=schema, task=task, language="zh")
        formatted_output = parse_and_format_output(output=output, task_type=task)

        with open(output_path, 'a+', encoding='utf-8') as f:
            for entry in formatted_output:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"预测结果已添加到 {output_path} 文件中。")