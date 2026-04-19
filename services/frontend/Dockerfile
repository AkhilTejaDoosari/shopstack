# ShopStack Frontend — Nginx
# Minimal. Static files + config. That is all.
FROM nginx:1.24-alpine

# Remove the default nginx config and replace with ours
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the store UI
COPY html/ /usr/share/nginx/html/

EXPOSE 80

# nginx starts automatically as the default CMD — no override needed
