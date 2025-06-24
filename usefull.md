```bash
curl http://localhost:11434/api/generate -d '{"model": "devstral", "keep_alive": 0}'
```
```bash
docker run -d \
  --name ollama \
  --gpus all \
  --network ollama-n8n-network \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e OLLAMA_FLASH_ATTENTION=1 \
  --tty \
  ollama/ollama:latest
```

```bash
docker run -d --gpus all \
  --name ollama \
  --network ollama-n8n-network \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  ollama-gpu


```
