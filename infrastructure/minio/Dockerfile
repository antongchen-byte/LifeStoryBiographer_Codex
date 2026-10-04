# MinIO Community is distributed as source. Build the pinned upstream release.
FROM golang:1.25 AS build
ENV CGO_ENABLED=0 GOMAXPROCS=4
RUN go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /go/bin/minio /usr/local/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
