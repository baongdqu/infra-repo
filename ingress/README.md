# 🌐 Hướng Dẫn Bootstrap GitOps, Sealed Secrets & Ingress/TLS (Phần 3)

## 1. Thứ tự Bootstrap chuẩn sau `terraform apply` (Tránh lỗi Race Condition)
Mỗi lần dựng mới AKS cluster (hoặc sau khi `terraform destroy`), thực hiện đúng 3 bước sau:

1. **Khởi tạo hạ tầng AKS + cài ArgoCD** (Phần 2):
   ```powershell
   terraform apply
   az aks get-credentials --resource-group <RG> --name <AKS_NAME>
   ```
2. **Khôi phục Master Key của Sealed Secrets TRƯỚC KHI chạy App-of-Apps** *(nếu đã từng backup)*:
   ```powershell
   .\infra-repo\k8s\scripts\seal-secrets.ps1 restore-key
   ```
   *(Nếu đây là lần đầu tiên chưa từng có key, bỏ qua bước 2; sau khi `sealed-secrets` chạy lên ở bước 3 hãy chạy `seal-secrets.ps1 seal` và `seal-secrets.ps1 backup-key` để lưu key cho những lần sau).*
3. **Kích hoạt ArgoCD App-of-Apps**:
   ```powershell
   kubectl apply -f infra-repo/argocd/root-app.yaml
   ```

---

## 2. Cấu hình Domain `nip.io` (hoặc Domain thật) & Let's Encrypt TLS
1. Cập nhật email của bạn trong [`cluster-issuers.yaml`](cluster-issuers.yaml) trước khi dùng `letsencrypt-prod`.
2. Sau khi `ingress-nginx` nhận External IP trên Azure LoadBalancer, lấy IP:
   ```powershell
   kubectl get svc -n ingress-nginx ingress-nginx-controller
   ```
3. Thay `REPLACE_LB_IP` trong:
   - `infra-repo/k8s/overlays/dev/kustomization.yaml` → `dev.<EXTERNAL_IP>.nip.io`
   - `infra-repo/k8s/overlays/production/kustomization.yaml` → `prod.<EXTERNAL_IP>.nip.io`
   *(Hoặc thay trực tiếp bằng domain thật như `dev.yourdomain.xyz` và `yourdomain.xyz`).*
4. Kiểm chứng chứng chỉ TLS:
   ```powershell
   kubectl get certificate -A
   curl -vk https://dev.<EXTERNAL_IP>.nip.io
   curl -v https://prod.<EXTERNAL_IP>.nip.io
   ```

---

## 3. Lưu ý GHCR Image Visibility
Mặc định GitHub Packages (GHCR) để image ở chế độ **Private** sau lần push đầu tiên. Sau khi Phần 2 push image lần đầu, cần vào GitHub Packages của `app-repo/frontend` và `app-repo/backend` chuyển sang **Public** để AKS pull được mà không bị `ImagePullBackOff`.
