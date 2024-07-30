# Retrieval-Augmented Generation (RAG) Documentation

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Introduction

## Introduction

RAG (Retrieval-Augmented Generation) is a powerful framework that combines the strengths of both retrieval-based and generation-based models in natural language processing. It enables the generation of high-quality responses by leveraging pre-existing knowledge from large-scale text corpora.

With RAG, you can retrieve relevant information from a knowledge source and use it to generate coherent and contextually appropriate responses. This approach allows for more accurate and informative outputs compared to traditional generation models.

RAG is particularly useful in tasks such as question answering, dialogue systems, and content generation. By incorporating retrieval into the generation process, it enhances the model's ability to provide accurate and well-informed responses.

In this README, you will find detailed instructions on how to install RAG, examples of its usage, guidelines for contributing to the project, and information about the license under which RAG is distributed.

Get started with RAG and unlock the potential of retrieval-augmented generation in your natural language processing projects.

## Installation

We use Docker based solution to run the code. You can use the following commands to build the docker image and run the code.

### Step 1: Create persistent volume for Weaviate data

```bash
docker volume create weaviate-data
```

### Step 2: Create network for Weaviate container

```bash
# Create a Docker network (optional, but recommended)
docker network create weaviate-network
```

### Step 3: Check docker compose file for Weaviate container

```bash
version: '3.8'

services:
  weaviate:
    image: semitechnologies/weaviate:latest
    container_name: weaviate
    ports:
      - "8080:8080"
    environment:
      QUERY_DEFAULTS_LIMIT: 100
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: "/var/lib/weaviate"
      ENABLE_MODULES: 'text2vec-cohere,text2vec-huggingface,text2vec-palm,text2vec-openai,generative-openai,generative-cohere,generative-palm,ref2vec-centroid,reranker-cohere,qna-openai'
    volumes:
      - weaviate-data:/var/lib/weaviate
    networks:
      - weaviate-network

volumes:
  weaviate-data:
    external: true

networks:
  weaviate-network:
    driver: bridge

```

### Step 4: Run the Weaviate container

```bash
docker-compose up -d
```

Note: Run `docker-compose down` to stop the container.

Check installation by opening the following URL in your browser: http://localhost:8080/v1/meta

## Usage from Python

We will use poetry to manage the dependencies.

With the following command you can install dependencies.

```bash
poetry install --no-root
```

Run the project with the following command.

```bash
poetry run python main.py
```

## Contributing

[Provide guidelines for contributing to RAG.]

## License

[Specify the license under which RAG is distributed.]
