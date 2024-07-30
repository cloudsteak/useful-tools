# Docker Compose Installation Guide for Jupyter Server

This guide will walk you through the steps to install Jupyter Server using Docker Compose.

## Prerequisites

Before you begin, make sure you have the following installed on your system:

- Docker
- Docker Compose

# Step 1: Create a Docker Volume

Run the following command to create a Docker volume for the Jupyter data:

```bash
docker volume create jupyter_data
```

## Step 2: Generate a Jupyter Token

Open a terminal and run the following command to generate a Jupyter token:

```bash
export TOKEN=$(openssl rand -hex 32)
echo $TOKEN
```

## Step 3: Create a Docker Compose file

Create a new file called `docker-compose.yml` in your project directory and add the following content:

```yaml
version: "3"
services:
  jupyter:
    image: jupyter/datascience-notebook
    ports:
      - "8888:8888"
    volumes:
      - jupyter_data:/home/jovyan
    environment:
      - JUPYTER_TOKEN=${TOKEN} # Optional: replace with a secure token if you want to avoid using the auto-generated token

volumes:
  jupyter_data:
    external: false
```

## Step 4: Start the Jupyter Server

Open a terminal and navigate to your project directory. Run the following command to start the Jupyter Server:

```bash
docker-compose up -d
```

## Step 5: Access Jupyter Server

Once the server is up and running, you can access it by opening your web browser and navigating to `http://localhost:8888`. You will be prompted to enter a token, which can be found in the terminal output.

## Step 6: Stop the Jupyter Server

To stop the Jupyter Server, go back to the terminal and run the following command:

```bash
docker-compose down
```

This will gracefully stop the server and clean up the resources.
