

n8n-start:
    docker run -it --rm \
    --name n8n \
    -p 5678:5678 \
    -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
    -e N8N_RUNNERS_ENABLED=true \
    -v ./data:/home/node/.n8n \
    docker.n8n.io/n8nio/n8n
