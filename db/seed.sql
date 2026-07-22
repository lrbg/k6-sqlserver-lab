-- Esquema semilla del laboratorio (ventas). Requiere SQL Server 2022 (GENERATE_SERIES).
IF DB_ID('perflab') IS NULL CREATE DATABASE perflab;
GO
USE perflab;
GO
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
GO

CREATE TABLE customers (
    id       INT PRIMARY KEY,
    name     NVARCHAR(100),
    city     NVARCHAR(50),
    created  DATETIME2
);
CREATE TABLE products (
    id       INT PRIMARY KEY,
    name     NVARCHAR(100),
    price    DECIMAL(10,2),
    category NVARCHAR(40)
);
CREATE TABLE orders (
    id          INT PRIMARY KEY,
    customer_id INT,
    order_date  DATETIME2,
    total       DECIMAL(12,2)
);
CREATE TABLE order_items (
    id         INT PRIMARY KEY,
    order_id   INT,
    product_id INT,
    qty        INT,
    price      DECIMAL(10,2)
);
GO

-- Datos: 5k clientes, 500 productos, 20k ordenes, 60k renglones
INSERT INTO customers (id, name, city, created)
SELECT value, CONCAT('Cust', value),
       CHOOSE(1 + value % 5, 'CDMX','GDL','MTY','PUE','QRO'),
       DATEADD(day, -(value % 365), SYSDATETIME())
FROM GENERATE_SERIES(1, 5000);

INSERT INTO products (id, name, price, category)
SELECT value, CONCAT('Prod', value), 10 + (value % 500),
       CHOOSE(1 + value % 4, 'A','B','C','D')
FROM GENERATE_SERIES(1, 500);

INSERT INTO orders (id, customer_id, order_date, total)
SELECT value, 1 + ABS(CHECKSUM(NEWID())) % 5000,
       DATEADD(minute, -value, SYSDATETIME()), 0
FROM GENERATE_SERIES(1, 20000);

INSERT INTO order_items (id, order_id, product_id, qty, price)
SELECT value, 1 + ABS(CHECKSUM(NEWID())) % 20000,
       1 + ABS(CHECKSUM(NEWID())) % 500,
       1 + value % 5, 10 + (value % 490)
FROM GENERATE_SERIES(1, 60000);
GO

CREATE INDEX ix_orders_customer ON orders(customer_id);
CREATE INDEX ix_items_order      ON order_items(order_id);
CREATE INDEX ix_customers_city   ON customers(city);
GO

PRINT 'Seed completo';
GO
