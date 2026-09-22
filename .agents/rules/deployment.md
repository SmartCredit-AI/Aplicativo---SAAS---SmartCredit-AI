# Diretriz Obrigatória: Sincronização e Deploy Contínuo

Sempre após realizar alterações, correções ou implementações no projeto SmartCredit-AI, executar obrigatoriamente as etapas de sincronização com **GitHub**, **Vercel** e **Supabase**:

## 1. GitHub
- Adicionar todos os arquivos modificados:
  ```powershell
  git add .
  ```
- Criar commit descritivo:
  ```powershell
  git commit -m "tipo: mensagem descritiva da alteração"
  ```
- Enviar as alterações para o repositório remoto:
  ```powershell
  git push origin main
  ```

## 2. Vercel
- O repositório está integrado à Vercel com base no arquivo `vercel.json`.
- Cada push na branch `main` do GitHub dispara automaticamente o build e deploy na Vercel.
- Caso necessário deploy forçado ou manual:
  ```cmd
  cmd /c "npx vercel --prod"
  ```

## 3. Supabase
- Se houver alterações em migrations (`supabase/migrations/*.sql`), schemas ou configurações do Supabase:
  ```cmd
  cmd /c "npx supabase db push"
  ```
- Para verificar status das migrações:
  ```cmd
  cmd /c "npx supabase migration list"
  ```
