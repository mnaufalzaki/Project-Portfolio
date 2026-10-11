-- ShowUp: satu baris = satu habit selesai pada satu hari (tanggal lokal perangkat).
-- Jalankan sekali di Supabase → SQL Editor.

create table if not exists public.checkins (
  user_id    uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  habit      text        not null check (habit in ('study', 'read', 'wake', 'p')),
  day        date        not null,
  created_at timestamptz not null default now(),
  primary key (user_id, habit, day)
);

alter table public.checkins enable row level security;

-- Hanya pemilik baris yang bisa membaca, menambah, dan menghapus datanya sendiri.
drop policy if exists "checkins_select_own" on public.checkins;
drop policy if exists "checkins_insert_own" on public.checkins;
drop policy if exists "checkins_delete_own" on public.checkins;

create policy "checkins_select_own" on public.checkins
  for select to authenticated using (auth.uid() = user_id);

create policy "checkins_insert_own" on public.checkins
  for insert to authenticated with check (auth.uid() = user_id);

create policy "checkins_delete_own" on public.checkins
  for delete to authenticated using (auth.uid() = user_id);
