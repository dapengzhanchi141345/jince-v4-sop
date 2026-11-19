"""
金策宗师团 — GPU训练自动化 (一键搞定)
不需要手动操作Kaggle, 此脚本自动完成:
  1. 检查/配置Kaggle API
  2. 创建Notebook
  3. 提交到Kaggle运行
  4. 等待训练完成
  5. 下载模型到本地
  6. 集成到引擎

用法:
  python run_gpu_training.py              # 完整流程
  python run_gpu_training.py --status     # 查看训练状态
  python run_gpu_training.py --download   # 只下载已完成的模型
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = "E:/GoldstrategyEngine"
KAGGLE_NOTEBOOK = f"{BASE_DIR}/integrations/kaggle_notebook.ipynb"
MODEL_DIR = f"{BASE_DIR}/data/models"
KAGGLE_WORKING = "/kaggle/working"

# Kaggle配置
KAGGLE_DATASET = "goldstrategy-guild-training"
KAGGLE_NOTEBOOK_NAME = "goldstrategy-lstm-training"


def check_kaggle_setup() -> bool:
    """
    检查Kaggle API是否配置
    
    如果需要配置:
      1. 去 https://www.kaggle.com/settings 创建API Token
      2. 下载 kaggle.json 放到 ~/.kaggle/
    """
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_json = kaggle_dir / "kaggle.json"
    
    if kaggle_json.exists():
        print("  ✅ Kaggle API 已配置")
        return True
    
    print(f"\n  ⚠️ Kaggle API 未配置")
    print(f"  需要您操作一次 (以后就不用管了):")
    print(f"  ───────────────────────────────────────")
    print(f"  1. 打开 https://www.kaggle.com")
    print(f"  2. 注册/登录 → 右上角头像 → Settings")
    print(f"  3. 找到 API → Create New Token")
    print(f"  4. 下载 kaggle.json 文件")
    print(f"  5. 把文件放到 {kaggle_json}")
    print(f"  ───────────────────────────────────────")
    print(f"  放好后重新运行这个脚本即可自动完成全部训练。")
    
    return False


def install_kaggle_cli():
    """确保kaggle CLI可用"""
    try:
        subprocess.run(["kaggle", "--version"], capture_output=True, creationflags=0x08000000)
        return True
    except FileNotFoundError:
        print("  ⚠️ 安装kaggle CLI...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "kaggle"
        ], capture_output=True, creationflags=0x08000000)
        return True


def push_and_run_notebook() -> bool:
    """
    推送Notebook到Kaggle并启动训练
    
    流程:
      1. 创建数据集 (训练数据)
      2. 推送Notebook到Kaggle
      3. 启动训练
      4. 监控进度
      5. 下载结果
    """
    print(f"\n{'='*50}")
    print(f"  🚀 提交训练到Kaggle GPU")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    # 确保目录
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # 1. 推送到Kaggle
    print("\n[1/4] 上传Notebook到Kaggle...")
    
    # 使用kaggle API创建Notebook
    # 注意: kaggle notebooks push 需要先创建kernel.json
    import nbformat
    from kagglehub import notebook_upload, notebook_run
    
    try:
        # 读取Notebook
        with open(KAGGLE_NOTEBOOK, 'r', encoding='utf-8') as f:
            notebook_content = f.read()
        
        # 上传到Kaggle
        result = notebook_upload(
            notebook_content=notebook_content,
            title=KAGGLE_NOTEBOOK_NAME,
            is_private=True,
        )
        
        print(f"  ✅ Notebook已上传")
        
        # 2. 启动训练
        print("\n[2/4] 启动GPU训练...")
        print("  (预计30-45分钟, Kaggle免费T4×2 GPU)")
        
        run_result = notebook_run(
            title=KAGGLE_NOTEBOOK_NAME,
            accelerator="GPU",
        )
        
        run_id = run_result.get("run_id")
        print(f"  ✅ 训练已启动 (ID: {run_id})")
        
        # 3. 监控进度
        print("\n[3/4] 监控训练进度...")
        print("  (每30秒检查一次, 耐心等待...)")
        
        from kagglehub import notebook_run_status
        
        while True:
            status = notebook_run_status(run_id)
            state = status.get("state", "")
            
            if state == "complete":
                print(f"  ✅ 训练完成!")
                break
            elif state == "error":
                print(f"  ❌ 训练失败: {status.get('error', 'unknown')}")
                return False
            elif state == "running":
                elapsed = status.get("elapsed_minutes", 0)
                progress = status.get("progress", 0)
                print(f"  ⏳ 运行中... {elapsed:.0f}分钟, {progress:.0f}%")
            
            time.sleep(30)
        
        # 4. 下载模型
        print("\n[4/4] 下载模型到本地...")
        
        from kagglehub import notebook_output_download
        
        output_path = notebook_output_download(run_id)
        
        if output_path:
            # 复制模型文件到本地
            import shutil
            for f in ["gold_lstm_model.h5", "gold_lstm_scaler.pkl", "model_config.json"]:
                src = os.path.join(output_path, f)
                dst = os.path.join(MODEL_DIR, f)
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    size_mb = os.path.getsize(dst) / 1024 / 1024
                    print(f"  ✅ {f}: {size_mb:.1f}MB")
            
            print(f"\n  🎯 模型已部署到: {MODEL_DIR}")
            return True
        else:
            print(f"  ❌ 下载失败")
            return False
            
    except Exception as e:
        print(f"\n  ❌ Kaggle交互失败: {e}")
        print(f"\n  📋 自动方案B: 手动导入")
        print(f"  1. 打开 https://www.kaggle.com/notebooks")
        print(f"  2. 点击 'New Notebook'")
        print(f"  3. 导入 {KAGGLE_NOTEBOOK}")
        print(f"  4. 选择 GPU 加速器 → 运行")
        print(f"  5. 下载输出的模型文件到 {MODEL_DIR}")
        return False


def download_existing_model() -> bool:
    """直接下载已训练好的模型 (不重新训练)"""
    print(f"\n{'='*50}")
    print(f"  从Kaggle下载已训练的模型")
    print(f"{'='*50}")
    
    from kagglehub import notebook_output_download
    
    try:
        result = notebook_output_download(name=KAGGLE_NOTEBOOK_NAME)
        if result:
            import shutil
            for f in ["gold_lstm_model.h5", "gold_lstm_scaler.pkl"]:
                src = os.path.join(result, f)
                dst = os.path.join(MODEL_DIR, f)
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    print(f"  ✅ {f}")
            print(f"  ✅ 下载完成")
            return True
    except Exception:
        pass
    
    print("  ❌ 未找到已训练的模型, 请先运行完整训练流程")
    return False


def show_status() -> dict:
    """查看模型状态"""
    model_path = f"{MODEL_DIR}/gold_lstm_model.h5"
    config_path = f"{MODEL_DIR}/model_config.json"
    
    if os.path.exists(model_path):
        size_mb = os.path.getsize(model_path) / 1024 / 1024
        mtime = datetime.fromtimestamp(os.path.getmtime(model_path))
        
        print(f"\n{'='*50}")
        print(f"  📊 GPU模型状态")
        print(f"{'='*50}")
        print(f"  模型: {'✅' if os.path.exists(model_path) else '❌'} LSTM")
        print(f"  大小: {size_mb:.1f}MB")
        print(f"  训练时间: {mtime.strftime('%Y-%m-%d %H:%M')}")
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            print(f"  准确率: {config.get('accuracy', 'N/A'):.1%}")
            print(f"  F1分数: {config.get('f1', 'N/A')}")
            print(f"  特征: {config.get('features', [])}")
        
        return {
            "available": True,
            "path": model_path,
            "size_mb": round(size_mb, 1),
            "trained_at": mtime.isoformat(),
        }
    else:
        print(f"\n  ❌ 模型未训练")
        print(f"  运行: python {__file__}")
        print(f"  或手动: 打开 {KAGGLE_NOTEBOOK} → 拖到Kaggle → 运行")
        return {"available": False}


def integrate_to_engine():
    """将训练的模型集成到引擎"""
    model_path = f"{MODEL_DIR}/gold_lstm_model.h5"
    scaler_path = f"{MODEL_DIR}/gold_lstm_scaler.pkl"
    
    if not os.path.exists(model_path):
        print("  ⚠️ 模型不存在, 跳过集成")
        return
    
    # 创建模型加载器
    loader_code = '''
import os
import joblib
import numpy as np
from tensorflow.keras.models import load_model

class LSTMPredictor:
    """LSTM预测器 — 自动加载训练好的模型"""
    
    def __init__(self):
        self.model = None
        self.scaler = None
        self._load()
    
    def _load(self):
        base = "E:/GoldstrategyEngine/data/models"
        model_path = f"{base}/gold_lstm_model.h5"
        scaler_path = f"{base}/gold_lstm_scaler.pkl"
        
        if os.path.exists(model_path):
            self.model = load_model(model_path)
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)
            print(f"[LSTM] 模型已加载")
    
    def predict(self, df):
        if self.model is None:
            return {"direction": "UNKNOWN", "probability": 0.5}
        try:
            data = df.copy()
            data["returns"] = data["close"].pct_change()
            data["high_low"] = (data["high"] - data["low"]) / data["close"]
            data["volatility"] = data["returns"].rolling(20).std()
            data["sma_20"] = data["close"].rolling(20).mean()
            data["sma_50"] = data["close"].rolling(50).mean()
            data["ratio_20_50"] = data["sma_20"] / data["sma_50"]
            
            feat = ["close", "returns", "high_low", "volatility", "ratio_20_50"]
            last = data[feat].dropna().iloc[-60:].values
            
            if len(last) < 60:
                return {"direction": "UNKNOWN", "probability": 0.5}
            if self.scaler:
                last = self.scaler.transform(last)
            
            prob = float(self.model.predict(np.array([last]), verbose=0)[0][0])
            return {
                "direction": "UP" if prob > 0.5 else "DOWN",
                "probability": round(prob, 3),
                "confidence": round(abs(prob - 0.5) * 2, 3),
            }
        except Exception as e:
            return {"direction": "UNKNOWN", "probability": 0.5, "error": str(e)}
'''
    
    loader_path = f"{BASE_DIR}/integrations/lstm_predictor.py"
    with open(loader_path, 'w') as f:
        f.write(loader_code)
    
    print(f"  ✅ 预测器已生成: {loader_path}")
    print(f"  在引擎中调用: from integrations.lstm_predictor import LSTMPredictor")


def main():
    """主入口"""
    print(f"""
╔═══════════════════════════════════════════╗
║   金策宗师团 — GPU训练自动化               ║
║   Goldstrategy Guild — Auto GPU Training  ║
╚═══════════════════════════════════════════╝
    """)
    
    # 解析参数
    if "--status" in sys.argv:
        show_status()
        return
    
    if "--download" in sys.argv:
        download_existing_model()
        integrate_to_engine()
        return
    
    # 检查Kaggle配置
    if not check_kaggle_setup():
        return
    
    # 准备kaggle CLI
    install_kaggle_cli()
    
    # 推送并训练
    success = push_and_run_notebook()
    
    if success:
        # 集成到引擎
        print(f"\n{'='*50}")
        print(f"  将模型集成到金策宗师团...")
        integrate_to_engine()
        
        print(f"\n{'='*50}")
        print(f"  ✅ 全部完成!")
        print(f"  模型: {MODEL_DIR}/gold_lstm_model.h5")
        print(f"  预测器: {BASE_DIR}/integrations/lstm_predictor.py")
        print(f"  重启引擎后自动生效")
        print(f"{'='*50}")
    else:
        print(f"\n  ⚠️ 自动训练失败, 请手动操作:")
        print(f"  1. 打开 https://www.kaggle.com/notebooks")
        print(f"  2. 导入 {KAGGLE_NOTEBOOK}")
        print(f"  3. 运行完成后下载模型到 {MODEL_DIR}")
        print(f"  4. 运行: python {__file__} --download")


if __name__ == "__main__":
    main()
