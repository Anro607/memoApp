import sys
import os
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QFrame, QPushButton, QTextEdit, 
                             QTextBrowser, QStackedWidget, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QMenu,
                             QListWidget, QSizeGrip, QFileDialog, QStyledItemDelegate,
                             QStyle)
from PyQt6.QtGui import QPixmap, QAction, QTextDocument, QTextOption, QPainter, QIcon
from PyQt6.QtCore import (Qt, QPoint, QPropertyAnimation, QEasingCurve, QRect, QEvent, 
                            QSize, QSequentialAnimationGroup, QPointF, QVariantAnimation)
import json

"""
pyinstaller --noconsole --onefile --icon="icon.ico" --add-data "NanumGothic.ttf;." --name "CharacterMemoPad" custom_memo_app_win.py
"""



class WordWrapDelegate(QStyledItemDelegate):
    """
    QListWidget 내의 긴 파일명을 글자 단위로 강제 줄바꿈하여 표시하는 커스텀 델리게이트.
    """
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app


    def paint(self, painter, option, index):
        painter.save()

        # 1. 배경 및 선택 효과 그리기 (기본 텍스트 제외)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else QApplication.style()
        # CE_ItemViewItem 대신 패널 원시 요소만 그려서 기본 텍스트 렌더링 방지
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        # 2. 텍스트 색상 결정 (테마 적용: 선택 시 배경색 대비, 기본은 글자색)
        if option.state & QStyle.StateFlag.State_Selected:
            text_color = self.main_app.THEME_BG_COLOR
        else:
            text_color = self.main_app.THEME_TEXT_COLOR

        # 3. QTextDocument를 활용한 글자 단위 줄바꿈 렌더링
        doc = QTextDocument()
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(text_option)
        doc.setHtml(f"<div style='color:{text_color}; font-family:나눔고딕; font-size:14px;'>{index.data()}</div>")

        # 너비 계산 (충분한 여백 확보)
        if option.widget:
            available_width = option.widget.viewport().width() - 10
        else:
            available_width = 170
        available_width = max(available_width, 50)
        doc.setTextWidth(available_width)

        # 텍스트 위치 계산 및 그리기 (좌우 5px, 상하 1px 여백 반영)
        painter.translate(option.rect.left() + 5, option.rect.top() + 1)
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(text_option)

        # 크기 계산용 HTML (색상 제외)
        doc.setHtml(f"<div style='font-family:나눔고딕; font-size:14px;'>{index.data()}</div>")

        # 너비 계산 (paint와 일치)
        if option.widget:
            available_width = option.widget.viewport().width() - 10
        else:
            available_width = 170
        available_width = max(available_width, 50)
        doc.setTextWidth(available_width)
        # 정확한 높이 반환 (상하 1px씩 총 2px 여백 추가)
        return QSize(available_width, int(doc.size().height()) + 2)

class DraggableTopBar(QFrame):
    """
    캐릭터가 표시되는 상단 바 영역을 담당하는 클래스.
    QGraphicsView를 포함하며, 창 드래그 및 캐릭터 손 클릭 상호작용을 처리합니다.
    """
    def __init__(self, parent=None, view=None, toggle_mode_func=None, toggle_panel_func=None):
        super().__init__(parent)
        self.main_window = parent           # 참조용 메인 윈도우
        self.view = view                    # 캐릭터가 그려진 QGraphicsView
        self.toggle_mode = toggle_mode_func   # 왼쪽 손 클릭 시 실행할 함수
        self.toggle_panel = toggle_panel_func # 오른쪽 손 클릭 시 실행할 함수
        self.old_pos = None                 # 드래그용 좌표 기록

        # view의 viewport에서 마우스 이벤트를 가로채기 위한 이벤트 필터 설치
        self.view.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        """
        GraphicsView가 마우스 이벤트를 자체적으로 소비하는 것을 방지하기 위해 
        viewport의 이벤트를 감시하여 드래그 로직을 수행합니다.
        """
        if watched == self.view.viewport():
            if event.type() == QEvent.Type.MouseMove:
                # 마우스 이동 시 드래그 수행
                if self.old_pos is not None:
                    delta = event.globalPosition().toPoint() - self.old_pos
                    self.main_window.move(self.main_window.x() + delta.x(), self.main_window.y() + delta.y())
                    self.old_pos = event.globalPosition().toPoint()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                # 마우스 버튼 해제 시 드래그 상태 초기화
                self.old_pos = None
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        """
        상단 바 클릭 시 드래그 여부 판단 및 캐릭터 상호작용 처리.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # 1. 클릭 위치가 상단 바 영역(y <= 192)인지 확인
            if event.position().y() <= 192:
                # 전역 좌표를 GraphicsView 내의 씬 좌표로 변환하여 클릭된 아이템 확인
                view_pos = self.view.mapFromGlobal(event.globalPosition().toPoint())
                item = self.view.itemAt(view_pos)
                
        if item:
            data = item.data(0)
            if data == "hand1":
                self.toggle_mode()
                self._animate_hand_press(item)
                return  # 드래그로 이어지지 않게 중단
            elif data == "hand2":
                self.toggle_panel()
                self._animate_hand_press(item)
                return  # 드래그로 이어지지 않게 중단

        # 2. 손 아이템이 아니거나 상단 바 외부인 경우 창 드래그 시작 기록
        self.old_pos = event.globalPosition().toPoint()

    def _animate_hand_press(self, hand_item):
        """
        손 아이템을 클릭했을 때 '쿡' 누르는 느낌의 Jiggle 애니메이션 수행.
        연속 클릭 시 위치가 어긋나지 않도록 초기 위치로 리셋 로직 포함.
        """
        # 1. 기존 애니메이션이 실행 중이면 중지 및 위치 리셋
        if hasattr(self, 'press_anim') and self.press_anim.state() == QVariantAnimation.State.Running:
            self.press_anim.stop()

        # 2. 캐릭터 로딩 시 아이템에 저장해둔 홈(원래) 위치로 강제 복구
        home_pos = hand_item.data(1) 
        if home_pos is not None:
            hand_item.setPos(home_pos)
        else:
            home_pos = hand_item.pos()

        # 3. 새로운 애니메이션 설정
        down_pos = home_pos + QPointF(0, 7)

        self.press_anim = QVariantAnimation()
        self.press_anim.setDuration(160)
        self.press_anim.setStartValue(home_pos)
        self.press_anim.setKeyValueAt(0.5, down_pos)
        self.press_anim.setEndValue(home_pos)
        self.press_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # 값 변경 시마다 아이템 위치 업데이트
        self.press_anim.valueChanged.connect(hand_item.setPos)
        self.press_anim.start()
class CustomMemoApp(QMainWindow):
    """
    캐릭터가 메모장을 들고 있는 독특한 레이아웃의 마크다운 메모장 애플리케이션 클래스.
    수동 레이아웃 관리, 캐릭터 테마 시스템, 마크다운 렌더링 기능을 포함합니다.
    """
    def __init__(self):
        """
        애니메이션, UI 구성 요소, 테마 및 초기 설정을 초기화하는 생성자.
        """
        super().__init__()



        # 1. 초기 창 설정 및 프레임리스 테두리 제거
        self.base_path = get_base_path()
        self.setWindowIcon(QIcon(os.path.join(self.base_path, 'icon.ico')))
        self.setWindowTitle("CharacterMemoPad")

        self.setMinimumSize(500, 250)
        self.resize(500, 500)
        # 윈도우 타이틀 바를 제거하고 투명 배경을 활성화하여 캐릭터 외형을 부각함
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 2. 전역 변수 초기화
        self.memos_dir = os.path.join(self.base_path, 'memos')

        self.current_file_path = None
        self.always_on_top = False
        self.CONTENT_Y_START = 160 # 캐릭터와 메모장이 겹치기 시작하는 Y축 지점

        # 3. 테마 초기값 설정 (JSON 로드 전 기본값)
        self.THEME_BG_COLOR = 'yellow'
        self.THEME_TEXT_COLOR = 'black'

        # 4. 중앙 위젯 설정 (수동 레이아웃을 위해 레이아웃 매니저 미사용)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # [상단 영역] 캐릭터 캔버스 뷰를 먼저 생성
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 전용 드래그 클래스로 상단 바 생성 및 뷰 배치
        self.top_bar = DraggableTopBar(self, self.view, self.toggle_mode, self.toggle_panel)
        self.top_bar.setFixedHeight(192)
        self.top_bar.setObjectName("topBar")
        self.top_layout = QHBoxLayout(self.top_bar)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(0)
        self.top_layout.addWidget(self.view)
        
        # [하단 영역] 메모 내용이 표시되는 콘텐츠 영역 (상단과 오버랩됨)
        self.content_area = QFrame(self.central_widget)
        self.content_area.setObjectName("contentArea")
        self.content_layout = QVBoxLayout(self.content_area)
        # 상단 여백을 25px로 조정하여 캐릭터 손 바로 아래에 메모지가 위치하도록 설정
        self.content_layout.setContentsMargins(10, 25, 10, 10)


        # [우측 슬라이드 패널] 파일 목록 및 제어 버튼 패널
        self.right_panel = QFrame(self.central_widget)
        self.right_panel.setObjectName("rightPanel")
        self.panel_width = 180
        
        self.panel_layout = QVBoxLayout(self.right_panel)
        self.panel_layout.setContentsMargins(0, 30, 0, 30)
        
        #   메모 파일 리스트 위젯     
        self.file_list_widget = QListWidget()
        self.file_list_widget.setObjectName("fileList")
        self.file_list_widget.itemClicked.connect(self.load_selected_file)

        # 글자 단위 줄바꿈을 위한 커스텀 델리게이트 적용
        self.delegate = WordWrapDelegate(self.file_list_widget, self)
        self.file_list_widget.setItemDelegate(self.delegate)

        self.panel_layout.addWidget(self.file_list_widget)        
        # 버튼들을 상단으로 밀어올리기 위한 스트레치 추가
        self.panel_layout.addStretch()

        # 제어 버튼 직접 추가 (세로 배치)
        self.char_menu_btn = QPushButton("✨")
        self.char_menu_btn.setFixedSize(40, 40)
        self.char_menu_btn.clicked.connect(self.show_character_menu)
        self.panel_layout.addWidget(self.char_menu_btn)

        self.folder_btn = QPushButton("📂")
        self.folder_btn.setFixedSize(40, 40)
        self.folder_btn.clicked.connect(self.select_folder)
        self.panel_layout.addWidget(self.folder_btn)

        self.ontop_btn = QPushButton("📌")
        self.ontop_btn.setFixedSize(40, 40)
        self.ontop_btn.setObjectName("onTopButton")
        self.ontop_btn.clicked.connect(self.toggle_always_on_top)
        self.panel_layout.addWidget(self.ontop_btn)

        self.min_btn = QPushButton("—")
        self.min_btn.setFixedSize(40, 40)
        self.min_btn.clicked.connect(self.showMinimized)
        self.panel_layout.addWidget(self.min_btn)

        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(40, 40)
        self.close_btn.clicked.connect(self.close)
        self.panel_layout.addWidget(self.close_btn)

        # 패널 애니메이션 설정
        self.panel_expanded = False
        self.animation = QPropertyAnimation(self.right_panel, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # 에디터(편집) 모드와 브라우저(미리보기) 모드를 전환하는 스택 위젯
        self.stack = QStackedWidget()
        self.content_layout.addWidget(self.stack)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("빈 메모장 입니다.")
        self.editor.setAlignment(Qt.AlignmentFlag.AlignJustify)
        self.stack.addWidget(self.editor)

        self.browser = QTextBrowser()
        self.stack.addWidget(self.browser)

        # 창 크기 조절 핸들 (SizeGrip)
        self.grip_layout = QHBoxLayout()
        self.grip_layout.addStretch()
        self.size_grip = QSizeGrip(self.content_area)
        self.grip_layout.addWidget(self.size_grip)
        self.content_layout.addLayout(self.grip_layout)


        import html
        self.html_escape = html.escape

        # 5. 마크다운 처리용 정규식 컴파일
        self.bold_regex = re.compile(r'\*\*(.*?)\*\*')
        self.italic_regex = re.compile(r'\*(.*?)\*')
        self.link_regex = re.compile(r'\[(.*?)\]\((.*?)\)')
        self.h1_regex = re.compile(r'^#\s*(.+)$', re.MULTILINE)
        self.h2_regex = re.compile(r'^##\s*(.+)$', re.MULTILINE)
        self.h3_regex = re.compile(r'^###\s*(.+)$', re.MULTILINE)
        self.hr_regex = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$', re.MULTILINE)
        self.ul_item_regex = re.compile(r'^\s*[\-\*\+]\s+(.*)$', re.MULTILINE)
        self.ol_item_regex = re.compile(r'^\s*(\d+)\.\s+(.*)$', re.MULTILINE)


        # 6. 초기 로드 (캐릭터 탐색 및 파일 목록)
        self.current_character = self._find_first_character()
        if self.current_character:
            self.change_character(self.current_character)
        else:
            # 캐릭터가 없을 경우 기본 테마 적용 및 빈 씬 유지
            self.apply_theme('yellow', 'black')
            self.scene.clear()
        self.populate_file_list()


    def _find_first_character(self):
        """
        assets 폴더를 스캔하여 첫 번째 캐릭터 폴더 이름을 반환.
        없으면 None 반환.
        """
        assets_dir = os.path.join(self.base_path, 'assets')
        if os.path.exists(assets_dir):
            for name in os.listdir(assets_dir):
                path = os.path.join(assets_dir, name)
                if os.path.isdir(path):
                    return name
        return None


    def toggle_mode(self):
        """
        편집 모드(0)와 미리보기 모드(1)를 토글 함.
        미리보기로 전환 시 자동으로 내용을 저장하고 마크다운을 렌더링함.
        """
        if self.stack.currentIndex() == 0:
            self.update_preview()
        else:
            self.stack.setCurrentIndex(0)

    def toggle_panel(self):
        """
        우측 파일 관리 패널을 열거나 닫는 애니메이션 실행.
        너비 확장 방식(왼쪽에서 오른쪽으로)으로 애니메이션을 수행하며, 메모지 공간은 침범하지 않습니다.
        """
        curr_w = self.width()
        panel_y = self.CONTENT_Y_START
        panel_h = self.height() - panel_y
        memo_width = curr_w - self.panel_width

        if not self.panel_expanded:
            self.populate_file_list()
            # 패널이 고정 위치(memo_width)에서 너비가 0에서 panel_width로 확장됨
            start_rect = QRect(memo_width, panel_y, 0, panel_h)
            end_rect = QRect(memo_width, panel_y, self.panel_width, panel_h)
            self.panel_expanded = True
        else:
            # 패널이 고정 위치(memo_width)에서 너비가 panel_width에서 0으로 축소됨
            start_rect = QRect(memo_width, panel_y, self.panel_width, panel_h)
            end_rect = QRect(memo_width, panel_y, 0, panel_h)
            self.panel_expanded = False

        # 애니메이션 대상: right_panel
        self.animation = QPropertyAnimation(self.right_panel, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.setStartValue(start_rect)
        self.animation.setEndValue(end_rect)

        self.right_panel.show()
        self.right_panel.raise_()
        self.animation.start()

    def populate_file_list(self):
        """
        정해진 메모 디렉토리를 스캔하여 .txt 및 .md 파일을 리스트 위젯에 표시.
        """
        self.file_list_widget.clear()
        if not os.path.exists(self.memos_dir):
            os.makedirs(self.memos_dir)
        files = [f for f in os.listdir(self.memos_dir) if f.endswith(('.txt', '.md'))]
        for file in sorted(files):
            self.file_list_widget.addItem(file)

    def load_selected_file(self, item):
        """
        파일 리스트에서 파일을 선택했을 때 내용을 읽어 에디터에 설정하고 즉시 미리보기 실행.
        """
        filename = item.text()
        self.current_file_path = os.path.join(self.memos_dir, filename)
        try:
            with open(self.current_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.editor.setPlainText(content)
                self.update_preview()
        except Exception as e:
            print(f"파일 로드 오류: {e}")

    def save_content(self):
        """
        현재 에디터의 내용을 물리 파일에 저장.
        """
        if self.current_file_path:
            content = self.editor.toPlainText()
            try:
                with open(self.current_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                print(f"저장 오류: {e}")

    def select_folder(self):
        """
        사용자가 메모가 저장될 작업 폴더를 직접 선택하도록 함.
        """
        selected = QFileDialog.getExistingDirectory(self, "메모 폴더 선택", self.memos_dir)
        if selected:
            self.memos_dir = selected
            self.current_file_path = None
            self.editor.clear()
            self.populate_file_list()

    def toggle_always_on_top(self):
        """
        애플리케이션 창이 다른 창보다 항상 위에 표시되도록 하는 기능 토글.
        """
        self.always_on_top = not self.always_on_top
        if self.always_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        
        # 버튼 상태 속성 업데이트 및 테마 재적용으로 스타일 갱신
        self.ontop_btn.setProperty("on", self.always_on_top)
        self.show()
        self.apply_theme()

    def show_character_menu(self):
        """
        assets 폴더의 캐릭터명 폴더들을 스캔하여 선택 가능한 메뉴를 팝업함.
        """
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background-color: {self.THEME_BG_COLOR}; color: {self.THEME_TEXT_COLOR}; border: 1px solid {self.THEME_TEXT_COLOR}; }} QMenu::item:selected {{ background-color: {self.THEME_TEXT_COLOR}; color: {self.THEME_BG_COLOR}; }}")
        assets_dir = os.path.join(self.base_path, 'assets')
        if os.path.exists(assets_dir):
            for char_name in os.listdir(assets_dir):
                if os.path.isdir(os.path.join(assets_dir, char_name)):
                    action = QAction(char_name, self)
                    action.triggered.connect(lambda checked, name=char_name: self.change_character(name))
                    menu.addAction(action)
        menu.exec(self.char_menu_btn.mapToGlobal(QPoint(0, self.char_menu_btn.height())))


    def load_character_theme(self, character_name):
        """
        캐릭터 폴더 내 theme.json 파일을 읽어 배경색, 글자색, 손 간격 데이터를 반환.
        """
        assets_path = os.path.join(self.base_path, 'assets', character_name)
        theme_file = os.path.join(assets_path, 'theme.json')
        default_theme = {'background': 'yellow', 'text': 'black', 'hand_gap': 100}
        if os.path.exists(theme_file):
            try:
                with open(theme_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {k: data.get(k, default_theme[k]) for k in default_theme}
            except: pass
        return default_theme



    def change_character(self, character_name):
        """
        선택된 캐릭터에 맞게 상단 씬(Scene)의 이미지를 교체하고 테마를 적용함.
        패널 예약 공간을 제외한 유효 너비를 기준으로 중앙을 계산합니다.
        """
        self.current_character = character_name
        theme = self.load_character_theme(character_name)
        self.scene.clear()
        assets_path = os.path.join(self.base_path, 'assets', character_name)


        # 머리(Head) 및 양손(Hand) 이미지 로드
        head_pix = QPixmap(os.path.join(assets_path, 'Head.png'))
        hand1_pix = QPixmap(os.path.join(assets_path, 'Hand1.png'))
        hand2_pix = QPixmap(os.path.join(assets_path, 'Hand2.png'))


        # 패널 공간을 제외한 유효 너비 계산
        effective_width = self.width() - self.panel_width
        view_h = 192
        self.scene.setSceneRect(0, 0, effective_width, view_h)
        center_x = effective_width / 2

        if not head_pix.isNull():
            # 머리 아이템 배치 (유효 중앙 기준)
            head_item = QGraphicsPixmapItem(head_pix)
            head_item.setPos(center_x - (head_pix.width() / 2), 0)
            self.scene.addItem(head_item)

        # 손 아이템 배치 및 기능 데이터(Tag) 주입
        hand_gap, hh = theme['hand_gap'], head_pix.height()
        if not hand1_pix.isNull():
            item = QGraphicsPixmapItem(hand1_pix)
            item.setData(0, "hand1")
            # 초기 '홈' 위치 저장 (연속 클릭 시 위치 복구용)
            h1_pos = QPointF(center_x - hand_gap - (hand1_pix.width() / 2), hh - (hand1_pix.height() / 2))
            item.setData(1, h1_pos)
            item.setData(2, QVariantAnimation()) # 개별 애니메이션 객체 할당
            item.setPos(h1_pos)
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            self.scene.addItem(item)
        if not hand2_pix.isNull():
            item = QGraphicsPixmapItem(hand2_pix)
            item.setData(0, "hand2")
            # 초기 '홈' 위치 저장 (연속 클릭 시 위치 복구용)
            h2_pos = QPointF(center_x + hand_gap - (hand2_pix.width() / 2), hh - (hand2_pix.height() / 2))
            item.setData(1, h2_pos)
            item.setData(2, QVariantAnimation()) # 개별 애니메이션 객체 할당
            item.setPos(h2_pos)
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            self.scene.addItem(item)
            self.apply_theme(theme['background'], theme['text'])

        # 미리보기 모드일 경우 테마 색상 변경 즉시 반영
        if self.stack.currentIndex() == 1:
            self.update_preview()



    def update_preview(self):
        """
        에디터의 마크다운 소스를 HTML로 변환하여 미리보기창에 표시함.
        블록 요소와 일반 텍스트를 지능적으로 구분하여 줄바꿈을 처리함.
        """
        self.save_content()
        raw_text = self.editor.toPlainText()

        # 1. HTML 이스케이프 (XSS 방지) - htmlLuv
        escaped_text = self.html_escape(raw_text)

        # 2. 인라인 요소 처리 (블록 처리 전 수행하여 충돌 방지)
        processed_text = self.bold_regex.sub(r'<b>\1</b>', escaped_text)
        # processed_text = self.bold_regex.sub(r'<b>\1</b>', raw_text)  #htmlLuv
        processed_text = self.italic_regex.sub(r'<i>\1</i>', processed_text)
        processed_text = self.link_regex.sub(r'<a href="\2" style="color:inherit;">\1</a>', processed_text)

        # 3. 블록 요소 및 텍스트 줄바꿈 지능형 처리
        lines = processed_text.split('\n')
        converted_lines = []
    
        for line in lines:
            # 제목 처리
            if self.h3_regex.match(line): line = self.h3_regex.sub(r'<h3>\1</h3>', line)
            elif self.h2_regex.match(line): line = self.h2_regex.sub(r'<h2>\1</h2>', line)
            elif self.h1_regex.match(line): line = self.h1_regex.sub(r'<h1>\1</h1>', line)
            # 가로선 처리
            elif self.hr_regex.match(line): line = self.hr_regex.sub(r'<hr>', line)
            # 리스트 아이템 처리
            elif self.ul_item_regex.match(line): line = self.ul_item_regex.sub(r'<li class="u-li">\1</li>', line)
            elif self.ol_item_regex.match(line): line = self.ol_item_regex.sub(r'<li class="o-li">\2</li>', line)

            # 일반 텍스트 또는 빈 줄: 개행을 보존하기 위해 <br> 처리
            else:
                if line.strip():
                    line += "<br>"
                else:
                    line = "<br>"

            converted_lines.append(line)
    
        processed_text = "".join(converted_lines)
        # 4. 리스트 그룹화 처리
        def wrap_list(text):
            text = re.sub(r'(<li class="u-li">.*?</li>(?:\s*<li class="u-li">.*?</li>)*)', 
                          r'<ul style="margin-top:0; margin-bottom:0;">\1</ul>', text, flags=re.DOTALL)
            text = re.sub(r'(<li class="o-li">.*?</li>(?:\s*<li class="o-li">.*?</li>)*)', 
                          r'<ol style="margin-top:0; margin-bottom:0;">\1</ol>', text, flags=re.DOTALL)
            text = text.replace(' class="u-li"', '').replace(' class="o-li"', '')
            return text

        processed_text = wrap_list(processed_text)

        self.browser.setHtml(f"<html><body style='text-align:justify; font-family: 나눔고딕; color: {self.THEME_TEXT_COLOR}; margin: 10px;'>{processed_text}</body></html>")
        # 미리보기 스택 페이지로 전환
        self.stack.setCurrentIndex(1)



    def apply_theme(self, bg_color=None, text_color=None):
        """
        QSS(Qt Style Sheets)를 사용하여 애플리케이션 전반의 색상 테마를 동적으로 변경함.
        """
        if bg_color: 
            self.THEME_BG_COLOR = bg_color
        if text_color: 
            self.THEME_TEXT_COLOR = text_color


        # QSizeGrip 커스텀 이미지 존재 여부 확인 (캐릭터별 assets 폴더 내 grip.png)
        grip_path = os.path.join(self.base_path, 'assets', self.current_character, 'Grip.png').replace('\\', '/')

        if os.path.exists(grip_path):
            grip_style = f"QSizeGrip {{ image: url({grip_path}); width: 20px; height: 20px; }}"
        else:
            grip_style = f"QSizeGrip {{ background-color: {self.THEME_TEXT_COLOR}; width: 20px; height: 20px; border-radius: 10px; }}"

        self.setStyleSheet(f"""
            #topBar, #rightPanel {{ background-color: transparent; }} 
            #rightPanel {{ background-color: transparent; border: none; }} 
            #contentArea {{ background-color: {self.THEME_BG_COLOR}; border: none; border-radius: 10px; }} 
            QPushButton {{
            background-color: {self.THEME_BG_COLOR};
            color: {self.THEME_TEXT_COLOR};
            border: none;
            padding: 5px;
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
            }}
            QPushButton:pressed {{
            background-color: {self.THEME_TEXT_COLOR};
            color: {self.THEME_BG_COLOR};
            border: 1px inset {self.THEME_TEXT_COLOR};
            padding: 3px;
            }}
            #onTopButton[on="true"] {{
            background-color: {self.THEME_TEXT_COLOR};
            color: {self.THEME_BG_COLOR};
            border: 1px inset {self.THEME_TEXT_COLOR};
            padding: 3px;
            }}
            QTextEdit, QTextBrowser {{
                background-color: transparent; 
                color: {self.THEME_TEXT_COLOR}; 
                border: none; 
                font-family: '나눔고딕', sans-serif;
                font-size: 14px; 
            }}
            QListWidget {{
                background-color: {self.THEME_BG_COLOR}; 
                color: {self.THEME_TEXT_COLOR}; 
                border: none; 
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
                font-family: '나눔고딕', sans-serif;
                font-size: 14px; 
                padding: 5px; 
            }}
            QListWidget::item {{
                padding: 1px 5px;
            }}
            QListWidget::item:selected {{
                background-color: {self.THEME_TEXT_COLOR}; 
                color: {self.THEME_BG_COLOR};
                border-radius: 5px;
            }}
            QScrollBar:horizontal {{
                height: 0px;
            }}
            QScrollBar::add-line:vertical {{
                height: 0px;
            }}
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:vertical {{
                background-color: {self.THEME_TEXT_COLOR};
                width: 12px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {self.THEME_TEXT_COLOR};
                border-radius: 3px;
                min-height: 5px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: {self.THEME_BG_COLOR};
            }}
            {grip_style}
                    """)

    def resizeEvent(self, event):
        """
        창 크기가 변하거나 패널이 토글될 때 위젯들의 위치 및 크기를 재배치함.
        고정 예약 공간 레이아웃: 패널이 나타나도 메모지나 캐릭터 바를 가리지 않습니다.
        """
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        
        # 1. 상단 바 및 콘텐츠 영역 너비: 패널 공간을 제외한 유효 너비 사용
        effective_width = w - self.panel_width
        self.top_bar.setGeometry(0, 0, effective_width, 192)
        
        panel_y = self.CONTENT_Y_START
        panel_h = h - panel_y
        
        # 2. 고정 레이아웃: content_area도 유효 너비만 사용
        self.content_area.setGeometry(0, panel_y, effective_width, panel_h)
        
        # 3. 우측 패널 위치 결정
        if self.panel_expanded:
            self.right_panel.setGeometry(effective_width, panel_y, self.panel_width, panel_h)
        else:
            self.right_panel.setGeometry(effective_width, panel_y, 0, panel_h)  

        # 항상 캐릭터(top_bar)를 다른 레이어보다 위로 올림
        self.top_bar.raise_()
        self.change_character(self.current_character)

def get_base_path():
    """
    Returns the directory containing the executable or script.
    Handles both development (script) and PyInstaller (bundled .exe) modes.
    """
    if getattr(sys, 'frozen', False):
        # Running as a bundled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as a script
        return os.path.dirname(__file__)

if __name__ == "__main__":
    # 애플리케이션 인스턴스 생성 및 창 표시
    app = QApplication(sys.argv)
    window = CustomMemoApp()
    window.show()
    sys.exit(app.exec())