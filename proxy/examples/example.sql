-- Example multi-statement payload that can be posted to the proxy.
CREATE TABLE demo_sink (
    id INT,
    payload STRING
) WITH (
    'connector' = 'blackhole'
);

INSERT INTO demo_sink
SELECT 1 AS id, 'hello from the proxy' AS payload;
