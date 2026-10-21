# Código LAUNCHER VISUALIZADOR Casimiro
# Autor: Bruno Levy
# CUBE DESIGN 2026

from adsb_viewer.src.main import main
import tkinter as tk
from tkinter import ttk, messagebox

class Client():
    def __init__(self, serial:str, web:str):
        if serial == "":
            raise ValueError("Porta serial nao pode estar em branco")
        self.serial = serial
        
        if web == "":
            self.web = 8000
        else:
            try:
                int(web)
            except:
                raise ValueError("Porta da interface Web nao eh valida")
            self.web = web

    def start_client(self):
        # TODO: Finish client starting
        main(["--replay",
              "/home/bruno/Documents/ITA/Cube/adsb_2u/solo/adsb_viewer/sample_data/example.log",
              "--replay-loop"])


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Launcher")
        self.geometry("480x300")

        ttk.Label(self, text = "Configuracoes", font=("Arial", 24)).pack(pady = 20)
        
        self.frame = ttk.Frame(self)
        self.frame.pack()

        ttk.Label(self.frame, text = "Porta Serial").grid(
                row = 0,
                column = 0,
                padx = 5,
                pady = 5,
                )

        self.serial_port = tk.StringVar()
        serial_entry = ttk.Entry(self.frame, width = 10, textvariable = self.serial_port).grid(
                row = 0,
                column = 1,
                padx = 5,
                pady = 5,
                )

        ttk.Label(self.frame, 
                  text = "Porta para inteface web \n(deixe em branco para usar o padrao)",
                  justify = "center").grid(
                row = 1,
                column = 0,
                padx = 5,
                pady = 5,
                )

        self.web_port = tk.StringVar()
        port_entry = ttk.Entry(self.frame, width = 10, textvariable = self.web_port).grid(
                row = 1,
                column = 1,
                padx = 5,
                pady = 5,
                )

        self.warning_label = ttk.Label(self, text = "", foreground = "red")
        self.warning_label.pack(pady = 10)

        ttk.Button(self, text = "Lancar", command = self.launch).pack(pady = 10)

    def launch(self):
        try:
            Client(serial = self.serial_port.get(), web = self.web_port.get()).start_client()
        except KeyboardInterrupt:
            pass
        except ValueError as e:
            self.warning_label.config(text = str(e))
        except Exception as e:
            self.warning_label.config(text = f"Erro inesperado: {str(e)}")

if __name__ == '__main__':
    LauncherApp().mainloop()
