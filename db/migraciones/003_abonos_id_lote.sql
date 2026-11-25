-- 003 — #64: ligar cada abono de fiado a su lote para poder cancelarlo (abonos.id_lote).
-- Ya aplicada en Aiven (confirmado en el dump del 25 nov 2026).
-- Solo para bases que aún no tengan la columna.
ALTER TABLE abonos
  ADD COLUMN id_lote varchar(20) DEFAULT NULL,
  ADD KEY idx_abonos_lote (id_tienda, id_lote);
