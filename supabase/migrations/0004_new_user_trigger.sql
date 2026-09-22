-- security definer + empty search_path: runs as the function owner (postgres)
-- so it can write public.profiles regardless of the caller's role, and every
-- reference is schema-qualified so nothing on the caller's path can hijack it.
create function public.handle_new_user() returns trigger
  language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
