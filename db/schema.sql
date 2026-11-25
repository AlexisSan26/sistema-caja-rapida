-- Caja Rápida — esquema de base de datos (MySQL 8.0), solo estructura, sin datos.
-- Generado el 25 nov 2026 a partir de un mysqldump de Aiven (defaultdb).
-- Uso: importar en un esquema VACÍO. No ejecutar contra producción.
-- productos.activo: 0 = inactivo, 1 = activo, 2 = archivado.

SET FOREIGN_KEY_CHECKS = 0;

-- tiendas
CREATE TABLE `tiendas` (
  `id_tienda` int NOT NULL AUTO_INCREMENT,
  `nombre_comercial` varchar(150) NOT NULL,
  `activa` tinyint(1) DEFAULT '1',
  `config_resumen` text,
  `dia_corte` int NOT NULL DEFAULT '1',
  `monto_mensual` decimal(10,2) NOT NULL DEFAULT '0.00',
  `estado_pago` enum('AL_DIA','ATRASADO') NOT NULL DEFAULT 'AL_DIA',
  PRIMARY KEY (`id_tienda`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- usuarios
CREATE TABLE `usuarios` (
  `id_usuario` int NOT NULL AUTO_INCREMENT,
  `id_tienda` int NOT NULL,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `rol` enum('superadmin','cajero') NOT NULL DEFAULT 'cajero',
  `activo` tinyint DEFAULT '1',
  `token_version` int NOT NULL DEFAULT '1',
  PRIMARY KEY (`id_usuario`),
  UNIQUE KEY `username` (`username`),
  KEY `fk_usuario_tienda` (`id_tienda`),
  CONSTRAINT `fk_usuario_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- productos_globales
CREATE TABLE `productos_globales` (
  `id_global` int NOT NULL AUTO_INCREMENT,
  `codigo_barras` varchar(50) NOT NULL,
  `nombre_producto` varchar(200) NOT NULL,
  `unidad_medida` varchar(20) NOT NULL DEFAULT 'pieza',
  `fecha_alta` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_global`),
  UNIQUE KEY `codigo_barras` (`codigo_barras`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- productos
CREATE TABLE `productos` (
  `id_producto` int NOT NULL AUTO_INCREMENT,
  `nombre_producto` varchar(150) NOT NULL,
  `precio_sugerido` decimal(10,2) NOT NULL,
  `precio_costo` decimal(10,2) DEFAULT NULL,
  `codigo_barras` varchar(30) DEFAULT NULL,
  `stock_actual` decimal(10,3) DEFAULT '0.000',
  `stock_minimo` decimal(10,3) DEFAULT '5.000',
  `proveedor` varchar(80) DEFAULT NULL,
  `fecha_caducidad` date DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `id_tienda` int NOT NULL,
  `unidad_medida` enum('pieza','kg','g','litro','ml','metro','paquete') NOT NULL DEFAULT 'pieza',
  `controla_stock` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id_producto`),
  UNIQUE KEY `unique_codigo_tienda` (`id_tienda`,`codigo_barras`),
  KEY `idx_codigo_barras` (`codigo_barras`),
  CONSTRAINT `fk_productos_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- turnos
CREATE TABLE `turnos` (
  `id_turno` int NOT NULL AUTO_INCREMENT,
  `fecha_apertura` datetime DEFAULT CURRENT_TIMESTAMP,
  `fecha_cierre` datetime DEFAULT NULL,
  `estado` enum('ABIERTO','CERRADO') NOT NULL,
  `id_tienda` int NOT NULL,
  `turno_activo` tinyint(1) DEFAULT NULL,
  `efectivo_declarado` decimal(10,2) DEFAULT NULL,
  `reglas_resumen_cerrado` text,
  PRIMARY KEY (`id_turno`),
  UNIQUE KEY `uk_tienda_turno_activo` (`id_tienda`,`turno_activo`),
  CONSTRAINT `fk_turnos_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- clientes
CREATE TABLE `clientes` (
  `id_cliente` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(120) NOT NULL,
  `telefono` varchar(15) DEFAULT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT '1',
  `id_tienda` int NOT NULL,
  `limite_credito` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id_cliente`),
  KEY `fk_clientes_tienda` (`id_tienda`),
  CONSTRAINT `fk_clientes_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- cuentas_fiado
CREATE TABLE `cuentas_fiado` (
  `id_cuenta` int NOT NULL AUTO_INCREMENT,
  `id_cliente` int NOT NULL,
  `estado` enum('ABIERTA','SALDADA') NOT NULL DEFAULT 'ABIERTA',
  `fecha_apertura` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id_tienda` int NOT NULL,
  PRIMARY KEY (`id_cuenta`),
  KEY `fk_cuenta_cliente` (`id_cliente`),
  KEY `fk_cuentas_tienda` (`id_tienda`),
  CONSTRAINT `fk_cuenta_cliente` FOREIGN KEY (`id_cliente`) REFERENCES `clientes` (`id_cliente`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_cuentas_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- detalle_fiado
CREATE TABLE `detalle_fiado` (
  `id_detalle` int NOT NULL AUTO_INCREMENT,
  `id_cuenta` int NOT NULL,
  `producto` varchar(120) NOT NULL,
  `cantidad` decimal(10,3) DEFAULT '1.000',
  `precio` decimal(10,2) NOT NULL,
  `monto_real` decimal(10,2) DEFAULT NULL,
  `fecha_hora` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id_tienda` int NOT NULL,
  PRIMARY KEY (`id_detalle`),
  KEY `fk_detalle_cuenta` (`id_cuenta`),
  KEY `fk_detalle_tienda` (`id_tienda`),
  CONSTRAINT `fk_detalle_cuenta` FOREIGN KEY (`id_cuenta`) REFERENCES `cuentas_fiado` (`id_cuenta`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_detalle_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- abonos
CREATE TABLE `abonos` (
  `id_abono` int NOT NULL AUTO_INCREMENT,
  `id_cuenta` int NOT NULL,
  `monto` decimal(10,2) NOT NULL,
  `nota` varchar(200) DEFAULT NULL,
  `fecha_hora` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `id_tienda` int NOT NULL,
  `metodo_pago` varchar(20) DEFAULT 'efectivo',
  `id_lote` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id_abono`),
  KEY `fk_abono_cuenta` (`id_cuenta`),
  KEY `idx_abonos_lote` (`id_tienda`,`id_lote`),
  CONSTRAINT `fk_abono_cuenta` FOREIGN KEY (`id_cuenta`) REFERENCES `cuentas_fiado` (`id_cuenta`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_abonos_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- movimientos
CREATE TABLE `movimientos` (
  `id_movimiento` int NOT NULL AUTO_INCREMENT,
  `id_turno` int NOT NULL,
  `fecha_hora` datetime DEFAULT CURRENT_TIMESTAMP,
  `tipo_movimiento` enum('VENTA','RETIRO','FONDO_CAJA','COBRO_FIADO') NOT NULL,
  `producto` varchar(150) DEFAULT NULL,
  `cantidad` decimal(10,3) DEFAULT '1.000',
  `cantidad_real` decimal(10,3) DEFAULT NULL,
  `id_producto_ref` int DEFAULT NULL,
  `metodo_pago` varchar(20) DEFAULT 'efectivo',
  `id_lote` varchar(20) DEFAULT NULL,
  `precio_unitario` decimal(10,2) NOT NULL,
  `total_movimiento` decimal(10,2) GENERATED ALWAYS AS ((`cantidad` * `precio_unitario`)) STORED,
  `id_tienda` int NOT NULL,
  PRIMARY KEY (`id_movimiento`),
  KEY `id_turno` (`id_turno`,`id_tienda`),
  KEY `idx_tienda_tipo` (`id_tienda`,`tipo_movimiento`),
  CONSTRAINT `fk_movimientos_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE,
  CONSTRAINT `movimientos_ibfk_1` FOREIGN KEY (`id_turno`) REFERENCES `turnos` (`id_turno`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- entradas_mercancia
CREATE TABLE `entradas_mercancia` (
  `id_entrada` int NOT NULL AUTO_INCREMENT,
  `id_producto` int NOT NULL,
  `cantidad` decimal(10,3) NOT NULL,
  `fecha_entrada` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `fecha_caducidad` date DEFAULT NULL,
  `notas` varchar(200) DEFAULT NULL,
  `id_tienda` int NOT NULL,
  `precio_costo` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id_entrada`),
  KEY `fk_entrada_prod` (`id_producto`),
  KEY `fk_entradas_tienda` (`id_tienda`),
  CONSTRAINT `fk_entrada_prod` FOREIGN KEY (`id_producto`) REFERENCES `productos` (`id_producto`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_entradas_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- log_auditoria
CREATE TABLE `log_auditoria` (
  `id_log` int NOT NULL AUTO_INCREMENT,
  `id_tienda` int NOT NULL,
  `id_usuario` int NOT NULL,
  `accion` varchar(50) NOT NULL,
  `detalle` text,
  `fecha_hora` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_log`),
  KEY `id_tienda` (`id_tienda`,`fecha_hora`),
  CONSTRAINT `fk_log_auditoria_tienda` FOREIGN KEY (`id_tienda`) REFERENCES `tiendas` (`id_tienda`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- operaciones_idempotentes
CREATE TABLE `operaciones_idempotentes` (
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

-- v_alertas
CREATE OR REPLACE VIEW `v_alertas` AS select `productos`.`nombre_producto` AS `nombre_producto`,`productos`.`codigo_barras` AS `codigo_barras`,`productos`.`proveedor` AS `proveedor`,`productos`.`stock_actual` AS `stock_actual`,`productos`.`stock_minimo` AS `stock_minimo`,`productos`.`fecha_caducidad` AS `fecha_caducidad`,(case when (`productos`.`stock_actual` <= `productos`.`stock_minimo`) then 'STOCK_BAJO' when ((`productos`.`fecha_caducidad` is not null) and (`productos`.`fecha_caducidad` <= (now() + interval 7 day))) then 'POR_CADUCAR' else 'OK' end) AS `alerta` from `productos` where ((`productos`.`activo` = 1) and ((`productos`.`stock_actual` <= `productos`.`stock_minimo`) or ((`productos`.`fecha_caducidad` is not null) and (`productos`.`fecha_caducidad` <= (now() + interval 7 day))))) order by (case when (`productos`.`stock_actual` <= `productos`.`stock_minimo`) then 'STOCK_BAJO' when ((`productos`.`fecha_caducidad` is not null) and (`productos`.`fecha_caducidad` <= (now() + interval 7 day))) then 'POR_CADUCAR' else 'OK' end) desc,`productos`.`fecha_caducidad`;

SET FOREIGN_KEY_CHECKS = 1;
