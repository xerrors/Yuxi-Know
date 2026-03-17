MODEL_DIR=/data/public/models
PORT=8081

TENSOR_PARALLEL_SIZE=1
export CUDA_VISIBLE_DEVICES="0"

source .venv/bin/activate

if [ -z "$1" ]; then
    echo "Error: No argument provided. Please specify a model name."
    exit 1
fi

if [ "$1" = "qwen3:32b" ]; then
    vllm serve "$MODEL_DIR/Qwen/Qwen3-32B" \
        --trust-remote-code \
        --device cuda --dtype auto --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
        --max_model_len 16384 \
        --served-model-name "$1" \
        --enable-auto-tool-choice \
        --tool-call-parser hermes \
        --host 0.0.0.0 --port $PORT
fi

# Qwen/Qwen3-Embedding-0.6B
if [ "$1" = "Qwen3-Embedding-0.6B" ]; then
    vllm serve "$MODEL_DIR/Qwen/Qwen3-Embedding-0.6B"  --task embed \
        --trust-remote-code --max_model_len 4096 \
        --device cuda --dtype auto --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
        --served-model-name "$1" --host 0.0.0.0 --port $PORT
fi

if [ "$1" = "Qwen3-Reranker-0.6B" ]; then
    vllm serve "$MODEL_DIR/Qwen/Qwen3-Reranker-0.6B" --task rerank \
        --trust-remote-code \
        --device cuda --dtype auto --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
        --max_model_len 4096 \
        --served-model-name "$1" --host 0.0.0.0 --port $PORT
fi






# https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html#named-arguments
# model	模型路径，以文件夹结尾
# tensor-parallel-size	张量并行副本数，即GPU的数量，咱这儿只有2张卡
# trust-remote-code	信任远程代码，主要是为了防止模型初始化时不能执行仓库中的源码，默认值是False
# device	用于执行 vLLM 的设备。可选auto、cuda、neuron、cpu
# gpu-memory-utilization	用于模型推理过程的显存占用比例，范围为0到1。例如0.5表示显存利用率为 50%。如果未指定，则将使用默认值 0.9。
# dtype	“auto”将对 FP16 和 FP32 型使用 FP16 精度，对 BF16 型使用 BF16 精度。
# “half”指FP16 的“一半”。推荐用于 AWQ 量化模型。
# “float16”与“half”相同。
# “bfloat16”用于在精度和范围之间取得平衡。
# “float”是 FP32 精度的简写。
# “float32”表示 FP32 精度。
# kv-cache-dtype	kv 缓存存储的数据类型。如果为“auto”，则将使用模型默认的数据类型。CUDA 11.8及以上版本 支持 fp8 （=fp8_e4m3） 和 fp8_e5m2。ROCm （AMD GPU） 支持 fp8 （=fp8_e4m3）
# served-model-name	对外提供的API中的模型名称
# host	监听的网络地址，0.0.0.0表示所有网卡的所有IP，127.0.0.1表示仅限本机
# port	API服务的端口
