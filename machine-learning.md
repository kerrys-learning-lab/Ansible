NOTE: 32b is too big :) ... although, i didn't have `--gpus all` passed in via Podman, so...

huggingface-cli download --local-dir <local_path> <repo_id> <filename.gguf>

Model Troubleshooting:
- qwen2.5-3b-instruct-q8_0.gguf - infinite loop:
    An infinite loop with Qwen Coder models in llama.cpp when used with clients like Roo Code is a known issue, primarily stemming from prompt format mismatches and tool-calling incompatibilities.

podman run  --gpus all \
            --rm \
            -it \
            --network host \
            -v /mnt/ml-models:/models
            ghcr.io/ggml-org/llama.cpp:full-cuda    --server \
                                                    --host 0.0.0.0 \
                                                    -m /models/gemma-3-12b-it-UD-Q4_K_XL.gguf



nvidia-5080
- Had to re-install Nvidia drivers after updgrade to 25.x
