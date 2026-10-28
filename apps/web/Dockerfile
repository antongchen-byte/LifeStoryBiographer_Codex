FROM node:22-alpine AS build
WORKDIR /srv
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG NEXT_PUBLIC_ENABLE_FILM_STUDIOS=true
ENV NEXT_PUBLIC_ENABLE_FILM_STUDIOS=$NEXT_PUBLIC_ENABLE_FILM_STUDIOS
RUN npm run build
FROM node:22-alpine
WORKDIR /srv
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /srv/.next/standalone ./
COPY --from=build --chown=node:node /srv/.next/static ./.next/static
COPY --from=build --chown=node:node /srv/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
