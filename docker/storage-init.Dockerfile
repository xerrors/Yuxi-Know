FROM alpine:3.20

COPY --chown=0:0 --chmod=0755 docker/storage-init.sh /usr/local/bin/storage-init

USER 0:0
ENTRYPOINT ["/usr/local/bin/storage-init"]
