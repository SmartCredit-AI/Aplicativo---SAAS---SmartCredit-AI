-- Migração para expandir a tabela de análises de crédito com contas contábeis e KPIs
alter table public.analises_credito
    add column if not exists razao_social text,
    add column if not exists ativo_total numeric(15, 2),
    add column if not exists ativo_circulante numeric(15, 2),
    add column if not exists passivo_circulante numeric(15, 2),
    add column if not exists patrimonio_liquido numeric(15, 2),
    add column if not exists lucro_liquido numeric(15, 2),
    add column if not exists ebitda numeric(15, 2),
    add column if not exists liquidez_seca numeric(10, 2),
    add column if not exists margem_ebitda numeric(10, 2),
    add column if not exists roe numeric(10, 2),
    add column if not exists capacidade_pagamento_mensal numeric(15, 2),
    add column if not exists rating text,
    add column if not exists dados_contabeis jsonb default '{}'::jsonb;
