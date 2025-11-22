# Widget Web — OCA Sistem Meteo

## Uso en cualquier web (HTML)
1. Sube `oca-widget.js` al hosting de tu web (o a /assets).
2. Inserta en la página donde quieras el widget:
```html
<script src="/ruta/oca-widget.js"></script>
<oca-meteo-widget api="https://TU_API" series="consumo_kwh" horizon="168"></oca-meteo-widget>
```
Atributos opcionales: `price="0.20" system="aerotermia"`.

## Demo local
Abre `index.html` con el backend en `http://localhost:8000`.
