import { useMutation, type UseMutationOptions } from "@tanstack/react-query";
import { useRef } from "react";

// 在 React 下一次渲染之前阻止双击重复写入，成功刷新或错误处理结束后再释放。
export function useLockedMutation<TData, TVariables>(options: UseMutationOptions<TData, Error, TVariables>) {
  const lock = useRef(false);
  const mutation = useMutation({ ...options, onSettled: async (...args) => {
    try { await options.onSettled?.(...args); }
    finally { lock.current = false; }
  } });
  return { ...mutation, mutate: (variables: TVariables) => {
    if (lock.current) return;
    lock.current = true;
    mutation.mutate(variables);
  } };
}
