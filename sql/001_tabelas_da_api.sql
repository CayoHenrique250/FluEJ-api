-- Tabelas lidas pela API (o app Android NÃO cadastra nada nelas; você preenche pelo painel do Supabase).
-- RLS ligado e SEM políticas: só a API (chave service_role) consegue ler.

create table if not exists public.avisos (
  id uuid primary key default gen_random_uuid(),
  titulo text not null,
  mensagem text not null default '',
  setor text,                       -- null = aviso para todos os setores
  criado_em timestamptz not null default now(),
  expira_em timestamptz             -- null = não expira
);

create table if not exists public.documentos_pendentes (
  id uuid primary key default gen_random_uuid(),
  setor text not null,
  titulo text not null,             -- ex.: 'Termos de voluntariado'
  quantidade integer not null default 0,
  atualizado_em timestamptz not null default now()
);

alter table public.avisos enable row level security;
alter table public.documentos_pendentes enable row level security;

-- Dados de exemplo (apague depois)
insert into public.avisos (titulo, mensagem, setor)
values ('Reunião geral', 'Sexta-feira, às 14h, na sala 3.', null);

insert into public.documentos_pendentes (setor, titulo, quantidade) values
  ('RH', 'Termos de voluntariado', 2),
  ('RH', 'Termos de encerramento', 5),
  ('Projetos', 'Termos de encerramento', 1);
