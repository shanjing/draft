
docker run --rm -it \
    --env-file /Users/shanjing/workspace/draft/.env.docker \
    -v /Users/shanjing/workspace/draft/.env:/app/.env:ro \
    -v /Users/shanjing/.draft:/home/app/.draft \
    -v /Users/shanjing/workspace/onnx_models:/app/onnx_models:ro \
    draft:onnx bash
