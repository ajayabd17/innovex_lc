pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  parameters {
    string(name: 'IMAGE_TAG', defaultValue: '', description: 'Optional image tag override (defaults to BUILD_NUMBER)')
    string(name: 'DOCKER_REPOSITORY', defaultValue: 'your-dockerhub-user', description: 'Registry namespace/repository owner')
    string(name: 'FRONTEND_API_URL', defaultValue: 'http://localhost:8000', description: 'Public backend URL for frontend build')
    string(name: 'CORS_ORIGINS', defaultValue: 'http://localhost:3000,http://127.0.0.1:3000', description: 'Allowed frontend origins for backend')
    booleanParam(name: 'PUSH_IMAGES', defaultValue: true, description: 'Push built images to container registry')
    booleanParam(name: 'DEPLOY', defaultValue: true, description: 'Deploy containers on Jenkins host after build')
  }

  environment {
    REGISTRY = 'docker.io'
    REPOSITORY = "${params.DOCKER_REPOSITORY}"
    EFFECTIVE_TAG = "${params.IMAGE_TAG ?: env.BUILD_NUMBER}"
    BACKEND_IMAGE = "${REGISTRY}/${REPOSITORY}/innovex-backend:${EFFECTIVE_TAG}"
    FRONTEND_IMAGE = "${REGISTRY}/${REPOSITORY}/innovex-frontend:${EFFECTIVE_TAG}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Backend Sanity') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              docker run --rm -v "$PWD/backend:/app" -w /app python:3.11-slim sh -lc "
                python -m compileall -q .
              "
            '''
          } else {
            powershell '''
              $backendPath = (Resolve-Path "backend").Path
              docker run --rm -v "${backendPath}:/app" -w /app python:3.11-slim sh -lc "python -m compileall -q ."
            '''
          }
        }
      }
    }

    stage('Frontend Build Sanity') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              docker build --target builder --build-arg NEXT_PUBLIC_API_BASE_URL="${FRONTEND_API_URL}" -t "${FRONTEND_IMAGE}-sanity" ./frontend
            '''
          } else {
            powershell '''
              docker build --target builder --build-arg NEXT_PUBLIC_API_BASE_URL="$env:FRONTEND_API_URL" -t "$($env:FRONTEND_IMAGE)-sanity" .\\frontend
            '''
          }
        }
      }
    }

    stage('Build Docker Images') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              docker build -t "$BACKEND_IMAGE" ./backend
              docker build --build-arg NEXT_PUBLIC_API_BASE_URL="${FRONTEND_API_URL}" -t "$FRONTEND_IMAGE" ./frontend
            '''
          } else {
            powershell '''
              docker build -t "$env:BACKEND_IMAGE" .\\backend
              docker build --build-arg NEXT_PUBLIC_API_BASE_URL="$env:FRONTEND_API_URL" -t "$env:FRONTEND_IMAGE" .\\frontend
            '''
          }
        }
      }
    }

    stage('Push Docker Images') {
      when { expression { return params.PUSH_IMAGES } }
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
          script {
            if (isUnix()) {
              sh '''
                echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                docker push "$BACKEND_IMAGE"
                docker push "$FRONTEND_IMAGE"
              '''
            } else {
              powershell '''
                $env:DOCKER_PASS | docker login -u "$env:DOCKER_USER" --password-stdin
                docker push "$env:BACKEND_IMAGE"
                docker push "$env:FRONTEND_IMAGE"
              '''
            }
          }
        }
      }
    }

    stage('Deploy') {
      when { expression { return params.DEPLOY } }
      steps {
        withCredentials([file(credentialsId: 'innovex-backend-env', variable: 'BACKEND_ENV_SECRET_FILE')]) {
          script {
            if (isUnix()) {
              sh '''
                mkdir -p backend/output
                cat > .jenkins.deploy.env <<EOF
BACKEND_IMAGE=${BACKEND_IMAGE}
FRONTEND_IMAGE=${FRONTEND_IMAGE}
BACKEND_ENV_FILE=${BACKEND_ENV_SECRET_FILE}
CORS_ORIGINS=${CORS_ORIGINS}
EOF
                docker compose -f infra/docker-compose.prod.yml --env-file .jenkins.deploy.env up -d --remove-orphans
              '''
            } else {
              powershell '''
                New-Item -ItemType Directory -Force -Path ".\\backend\\output" | Out-Null
                @"
BACKEND_IMAGE=$env:BACKEND_IMAGE
FRONTEND_IMAGE=$env:FRONTEND_IMAGE
BACKEND_ENV_FILE=$env:BACKEND_ENV_SECRET_FILE
CORS_ORIGINS=$env:CORS_ORIGINS
"@ | Set-Content -Path ".jenkins.deploy.env" -Encoding UTF8
                docker compose -f infra/docker-compose.prod.yml --env-file .jenkins.deploy.env up -d --remove-orphans
              '''
            }
          }
        }
      }
    }

    stage('Smoke Test') {
      when { expression { return params.DEPLOY } }
      steps {
        script {
          if (isUnix()) {
            sh '''
              sleep 10
              curl -fsS http://localhost:8000/v1/health
              curl -I -fsS http://localhost:3000
            '''
          } else {
            powershell '''
              Start-Sleep -Seconds 10
              Invoke-RestMethod -Uri "http://localhost:8000/v1/health" -Method Get | Out-Null
              Invoke-WebRequest -Uri "http://localhost:3000" -Method Head | Out-Null
            '''
          }
        }
      }
    }
  }

  post {
    always {
      script {
        if (isUnix()) {
          sh 'rm -f .jenkins.deploy.env || true'
        } else {
          powershell 'Remove-Item -ErrorAction SilentlyContinue ".jenkins.deploy.env"'
        }
      }
    }
  }
}
