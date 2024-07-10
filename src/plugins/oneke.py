# readmore: https://github.com/zjunlp/DeepKE/blob/main/example/llm/OneKE.md

import json
import torch
from transformers import (
    AutoConfig,
    AutoTokenizer,
    AutoModelForCausalLM,
    GenerationConfig,
    BitsAndBytesConfig
)

MODEL_NAME_OR_PATH = "zjunlp/OneKE"

instruction_mapper = {
    'NERzh': "你是专门进行实体抽取的专家。请从input中抽取出符合schema定义的实体，不存在的实体类型返回空列表。请按照JSON字符串的格式回答。",
    'REzh': "你是专门进行关系抽取的专家。请从input中抽取出符合schema定义的关系三元组，不存在的关系返回空列表。请按照JSON字符串的格式回答。",
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

    def __init__(self):
        self.config = AutoConfig.from_pretrained(MODEL_NAME_OR_PATH, trust_remote_code=True)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME_OR_PATH, trust_remote_code=True)

        # 4bit量化OneKE
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
            MODEL_NAME_OR_PATH,
            config=self.config,
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
            input_ids = self.tokenizer.encode(sintruct, return_tensors="pt")
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


if __name__ == "__main__":
    oneke = OneKE()
    text = "《红楼梦》是一部中国古典长篇小说，是清代作家曹雪芹创作的作品。"
    schema = ["人物", "地点", "时间", "事件"]
    output = oneke.predict(text, schema, "NER")
    print(output)