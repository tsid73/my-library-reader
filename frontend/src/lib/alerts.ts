import Swal from "sweetalert2";

// Dark-themed SweetAlert2 wrapper matching the app's palette.
const base = {
  background: "#161922",
  color: "#e9ebf0",
  confirmButtonColor: "#6d8bff",
  cancelButtonColor: "#2a3040",
};

export async function confirmAction(
  title: string,
  text?: string,
  confirmText = "Confirm"
): Promise<boolean> {
  const res = await Swal.fire({
    ...base,
    title,
    text,
    icon: "warning",
    showCancelButton: true,
    confirmButtonText: confirmText,
    cancelButtonText: "Cancel",
  });
  return res.isConfirmed;
}

export function toastError(message: string): void {
  Swal.fire({ ...base, title: "Something went wrong", text: message, icon: "error" });
}

export function toastOk(message: string): void {
  Swal.fire({
    ...base,
    toast: true,
    position: "top-end",
    timer: 1800,
    showConfirmButton: false,
    icon: "success",
    title: message,
  });
}

export async function promptText(
  title: string,
  value = "",
  placeholder = ""
): Promise<string | null> {
  const res = await Swal.fire({
    ...base,
    title,
    input: "text",
    inputValue: value,
    inputPlaceholder: placeholder,
    showCancelButton: true,
    confirmButtonText: "Save",
  });
  return res.isConfirmed ? (res.value as string).trim() : null;
}
