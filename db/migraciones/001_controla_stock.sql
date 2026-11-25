-- 001 — #114: casilla «No llevar control de existencias».
-- Ya aplicada en Aiven (confirmado en el dump del 25 nov 2026).
-- Solo sirve para bases que aún no tengan la columna (staging, copias locales viejas).
-- Los productos existentes quedan con controla_stock = 1 (sí llevan control).
ALTER TABLE productos
  ADD COLUMN controla_stock tinyint(1) NOT NULL DEFAULT '1';
