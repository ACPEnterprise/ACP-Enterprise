FROM node@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=/
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=$VITE_BASE_PATH

RUN npm run build

FROM nginx@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de AS runtime

RUN apk upgrade --no-cache

COPY nginx.preview.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/healthz || exit 1
