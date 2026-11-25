-- 002 — #66: idempotencia de ventas, abonos, fiados, entradas, mermas y retiros.
-- Ya aplicada en Aiven (confirmado en el dump del 25 nov 2026).
-- La usa helpers.py (_idem_reservar / _idem_guardar).
CREATE TABLE IF NOT EXISTS `operaciones_idempotentes` (
  `id_operacion` bigint NOT NULL AUTO_INCREMENT,
  `id_tienda` int NOT NULL,
  `clave` varchar(64) NOT NULL,
  `endpoint` varchar(40) NOT NULL,
  `respuesta` text,
  `creado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_operacion`),
  UNIQUE KEY `uk_idem_tienda_clave` (`id_tienda`,`clave`),
  KEY `idx_idem_creado` (`creado_en`),
  CONSTRAINT `fk_idem_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
